"""The six repair tools the Cascade Repairer fires in parallel.

Plain async functions wrapped with `function_tool` (the hello.py _get_weather
pattern) so tests call the plain function. Three Sabre-backed tools go
through the Sabre client layer (mock by default, SABRE_MODE=real on event
day); ground/dining/experience are simple canned mocks — no real provider
exists for them this phase.

Every tool writes through the existing repositories: a `bookings` row
carrying the provider payload as raw_response, and the `itinerary_items`
status transition (`booked` for the booking tool, `fixed` for repair tools).
Blocking BigQuery calls run via asyncio.to_thread — these tools execute on
the event loop that is also holding the live conversation. A failed or 0-row
write raises, so the completion event reports an error instead of a false ok.
"""
import asyncio
import hashlib

from agents import function_tool

from api.repositories import bookings, itinerary_items
from api.repositories.models import Booking
from api.sabre import client as sabre_client
from api.sabre import shapes

# Canned traveler for demo bookings — the demo trip has one traveler and the
# voice flow never collects passport-grade details.
_TRAVELER = shapes.TravelerRequest(givenName="Demo", surname="Traveler")
_CONTACT = shapes.ContactInfo(emails=["demo@example.com"], phones=["+16125550100"])


def _canned_ref(kind: str, item_id: str) -> str:
    """Deterministic confirmation ref for the non-Sabre category mocks."""
    digest = hashlib.sha256(f"{kind}|{item_id}".encode()).hexdigest().upper()
    return f"{kind[:3].upper()}-{digest[:8]}"


async def _write_booking_and_status(
    trip_id: str,
    item_id: str,
    sabre_ref: str,
    raw_response: dict,
    status: str,
) -> str:
    """The write path every tool shares: a bookings row with the provider
    payload, then the item's status flip. Raises on any failed or 0-row
    write so the repair never reports ok when nothing landed."""
    booking = Booking(
        item_id=item_id,
        trip_id=trip_id,
        sabre_confirmation_ref=sabre_ref,
        state="confirmed",
        raw_response=raw_response,
    )
    success, _, error = await asyncio.to_thread(bookings.create_booking, booking)
    if not success:
        raise RuntimeError(f"booking insert failed for item {item_id}: {error}")

    write_ok, affected_rows, write_error = await asyncio.to_thread(
        itinerary_items.update_status, item_id, status
    )
    if not write_ok:
        raise RuntimeError(
            f"status write failed for item {item_id} -> {status}: {write_error}"
        )
    if affected_rows == 0:
        raise RuntimeError(
            f"status write for item {item_id} -> {status} matched no rows"
        )
    return booking.booking_id


async def _latest_sabre_ref(trip_id: str, item_id: str) -> str:
    """The item's most recent Sabre confirmation ref, for cancel/modify calls.
    Falls back to a placeholder when no booking row exists (mock mode does
    not verify the ref)."""
    success, rows, error = await asyncio.to_thread(
        bookings.list_bookings_for_trip, trip_id
    )
    if not success:
        raise RuntimeError(f"booking lookup failed for trip {trip_id}: {error}")
    refs = [
        b.sabre_confirmation_ref
        for b in rows
        if b.item_id == item_id and b.sabre_confirmation_ref
    ]
    return refs[-1] if refs else "UNKNWN"


# --- Sabre-backed tools ---------------------------------------------------------

async def _search_and_book_flight(
    trip_id: str,
    item_id: str,
    origin: str,
    destination: str,
    departure_date: str,
) -> dict:
    """Search flights with Sabre (Bargain Finder Max) and book the best
    itinerary. Writes the booking and flips the itinerary item to `booked`.
    Returns the confirmation ref, flight number, times, and price."""
    search = await sabre_client.flight_search(
        shapes.FlightSearchRequest(
            OTA_AirLowFareSearchRQ=shapes.OTAAirLowFareSearchRQ(
                OriginDestinationInformation=[
                    shapes.OriginDestinationInformation(
                        RPH="1",
                        DepartureDateTime=f"{departure_date}T08:00:00",
                        OriginLocation=shapes.AirportLocation(LocationCode=origin),
                        DestinationLocation=shapes.AirportLocation(
                            LocationCode=destination
                        ),
                    )
                ],
                TravelerInfoSummary=shapes.TravelerInfoSummary(
                    AirTravelerAvail=[
                        shapes.AirTravelerAvail(
                            PassengerTypeQuantity=[
                                shapes.PassengerTypeQuantity(Code="ADT", Quantity=1)
                            ]
                        )
                    ]
                ),
            )
        )
    )
    gir = search.groupedItineraryResponse
    schedule = gir.scheduleDescs[0]
    fare = gir.itineraryGroups[0].itineraries[0].pricingInformation[0].fare

    booked = await sabre_client.create_booking(
        shapes.CreateBookingRequest(
            travelers=[_TRAVELER],
            contactInfo=_CONTACT,
            flightDetails=shapes.FlightDetails(
                flights=[
                    shapes.FlightToBook(
                        flightNumber=schedule.carrier.marketingFlightNumber,
                        airlineCode=schedule.carrier.marketing,
                        fromAirportCode=origin,
                        toAirportCode=destination,
                        departureDate=departure_date,
                        departureTime=schedule.departure.time[:5],
                    )
                ],
                flightPricing=[shapes.FlightPricing()],
            ),
        )
    )

    await _write_booking_and_status(
        trip_id, item_id, booked.confirmationId, booked.model_dump(), "booked"
    )
    flight = booked.booking.flights[0]
    return {
        "confirmation_ref": booked.confirmationId,
        "airline": flight.airlineCode,
        "flight_number": flight.flightNumber,
        "departure_date": flight.departureDate,
        "departure_time": flight.departureTime,
        "price": fare.totalFare.totalPrice,
        "currency": fare.totalFare.currency,
        "item_status": "booked",
    }


async def _rebook_flight(
    trip_id: str,
    item_id: str,
    origin: str,
    destination: str,
    departure_date: str,
) -> dict:
    """Rebook a broken flight: cancel the old Sabre booking and book a
    replacement (cancel + create — Sabre has no single rebook call). Writes
    the new booking and flips the itinerary item to `fixed`."""
    old_ref = await _latest_sabre_ref(trip_id, item_id)

    search = await sabre_client.flight_search(
        shapes.FlightSearchRequest(
            OTA_AirLowFareSearchRQ=shapes.OTAAirLowFareSearchRQ(
                OriginDestinationInformation=[
                    shapes.OriginDestinationInformation(
                        RPH="1",
                        DepartureDateTime=f"{departure_date}T08:00:00",
                        OriginLocation=shapes.AirportLocation(LocationCode=origin),
                        DestinationLocation=shapes.AirportLocation(
                            LocationCode=destination
                        ),
                    )
                ],
                TravelerInfoSummary=shapes.TravelerInfoSummary(
                    AirTravelerAvail=[
                        shapes.AirTravelerAvail(
                            PassengerTypeQuantity=[
                                shapes.PassengerTypeQuantity(Code="ADT", Quantity=1)
                            ]
                        )
                    ]
                ),
            )
        )
    )
    schedule = search.groupedItineraryResponse.scheduleDescs[0]
    fare = (
        search.groupedItineraryResponse.itineraryGroups[0]
        .itineraries[0].pricingInformation[0].fare
    )

    rebooked = await sabre_client.rebook_flight(
        shapes.RebookFlightRequest(
            confirmationId=old_ref,
            cancel=shapes.CancelBookingRequest(
                confirmationId=old_ref, cancelAll=True,
                errorHandlingPolicy="ALLOW_PARTIAL_CANCEL",
            ),
            create=shapes.CreateBookingRequest(
                travelers=[_TRAVELER],
                contactInfo=_CONTACT,
                flightDetails=shapes.FlightDetails(
                    flights=[
                        shapes.FlightToBook(
                            flightNumber=schedule.carrier.marketingFlightNumber,
                            airlineCode=schedule.carrier.marketing,
                            fromAirportCode=origin,
                            toAirportCode=destination,
                            departureDate=departure_date,
                            departureTime=schedule.departure.time[:5],
                        )
                    ],
                    flightPricing=[shapes.FlightPricing()],
                ),
            ),
        )
    )

    await _write_booking_and_status(
        trip_id, item_id, rebooked.created.confirmationId,
        rebooked.model_dump(), "fixed",
    )
    flight = rebooked.created.booking.flights[0]
    return {
        "cancelled_ref": old_ref,
        "confirmation_ref": rebooked.created.confirmationId,
        "airline": flight.airlineCode,
        "flight_number": flight.flightNumber,
        "departure_date": flight.departureDate,
        "departure_time": flight.departureTime,
        "price": fare.totalFare.totalPrice,
        "currency": fare.totalFare.currency,
        "item_status": "fixed",
    }


async def _shift_hotel_dates(
    trip_id: str,
    item_id: str,
    new_check_in: str,
    new_check_out: str,
) -> dict:
    """Move a hotel stay to new check-in/check-out dates via Sabre Modify
    Booking. Writes the updated booking and flips the itinerary item to
    `fixed`. Dates are YYYY-MM-DD."""
    old_ref = await _latest_sabre_ref(trip_id, item_id)

    modified = await sabre_client.modify_booking(
        shapes.ModifyBookingRequest(
            # The real flow fetches the signature from getBooking first; in
            # mock mode a placeholder is accepted. Event-day prep wires the
            # getBooking call into the real client.
            bookingSignature=f"sig-{old_ref}",
            confirmationId=old_ref,
            after=shapes.ModifyAfterState(
                hotels=[
                    shapes.HotelAfterState(
                        itemId="32",
                        checkInDate=new_check_in,
                        checkOutDate=new_check_out,
                        room=shapes.HotelRoomRequest(travelerIndices=[1]),
                    )
                ],
                travelers=[_TRAVELER],
            ),
        )
    )

    await _write_booking_and_status(
        trip_id, item_id, modified.confirmationId, modified.model_dump(), "fixed"
    )
    hotel = modified.booking.hotels[0]
    return {
        "confirmation_ref": modified.confirmationId,
        "hotel_name": hotel.hotelName,
        "check_in": hotel.checkInDate,
        "check_out": hotel.checkOutDate,
        "total": hotel.payment.total,
        "currency": hotel.payment.currencyCode,
        "item_status": "fixed",
    }


# --- Simple category mocks (no real provider this phase) ------------------------

async def _reschedule_ground(trip_id: str, item_id: str, new_pickup_time: str) -> dict:
    """Reschedule a ground transfer to a new pickup time. Canned mock — books
    the new pickup, flips the itinerary item to `fixed`."""
    ref = _canned_ref("ground", item_id)
    payload = {
        "provider": "mock-ground",
        "confirmation_ref": ref,
        "pickup_time": new_pickup_time,
        "vehicle": "standard sedan",
    }
    await _write_booking_and_status(trip_id, item_id, ref, payload, "fixed")
    return {
        "confirmation_ref": ref,
        "pickup_time": new_pickup_time,
        "item_status": "fixed",
    }


async def _move_dining(trip_id: str, item_id: str, new_time: str) -> dict:
    """Move a dining reservation to a new time. Canned mock — rebooks the
    table, flips the itinerary item to `fixed`."""
    ref = _canned_ref("dining", item_id)
    payload = {
        "provider": "mock-dining",
        "confirmation_ref": ref,
        "reservation_time": new_time,
        "party_size": 2,
    }
    await _write_booking_and_status(trip_id, item_id, ref, payload, "fixed")
    return {
        "confirmation_ref": ref,
        "reservation_time": new_time,
        "item_status": "fixed",
    }


async def _rebook_experience(trip_id: str, item_id: str, new_date: str) -> dict:
    """Rebook an experience/tour for a new date. Canned mock — issues new
    tickets, flips the itinerary item to `fixed`."""
    ref = _canned_ref("experience", item_id)
    payload = {
        "provider": "mock-experience",
        "confirmation_ref": ref,
        "date": new_date,
        "tickets": 2,
    }
    await _write_booking_and_status(trip_id, item_id, ref, payload, "fixed")
    return {
        "confirmation_ref": ref,
        "date": new_date,
        "item_status": "fixed",
    }


# function_tool-wrapped versions for the agent; tests call the plain functions.
# name_override strips the leading underscore from the LLM-facing tool name.
search_and_book_flight = function_tool(_search_and_book_flight, name_override="search_and_book_flight")
rebook_flight = function_tool(_rebook_flight, name_override="rebook_flight")
shift_hotel_dates = function_tool(_shift_hotel_dates, name_override="shift_hotel_dates")
reschedule_ground = function_tool(_reschedule_ground, name_override="reschedule_ground")
move_dining = function_tool(_move_dining, name_override="move_dining")
rebook_experience = function_tool(_rebook_experience, name_override="rebook_experience")

ALL_REPAIR_TOOLS = [
    search_and_book_flight,
    rebook_flight,
    shift_hotel_dates,
    reschedule_ground,
    move_dining,
    rebook_experience,
]
