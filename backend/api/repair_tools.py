"""The six repair tools the Cascade Repairer fires in parallel.

Plain async functions wrapped with `function_tool` (the hello.py _get_weather
pattern) so tests call the plain function. Three Sabre-backed tools go
through the Sabre client layer (mock by default, SABRE_MODE=real on event
day); ground/dining/experience are simple canned mocks — no real provider
exists for them this phase.

Every tool writes a `bookings` row carrying the provider payload as
raw_response through the existing repositories. Itinerary status transitions
are owned by a single writer (Phase 9 cleanup): the cascade unit
(`concurrency_core._repair_one`) walks `repairing` -> `fixed` around each
repair tool — the tools themselves no longer stamp `fixed`. The one
exception is `_search_and_book_flight`, an initial booking (not a repair)
with no cascade unit around it, which still flips its item to `booked`.
Blocking BigQuery calls run via asyncio.to_thread — these tools execute on
the event loop that is also holding the live conversation. A failed or 0-row
write raises, so the completion event reports an error instead of a false ok.
"""
import asyncio
import hashlib
import logging
from typing import List, Optional, Tuple

from agents import function_tool

from api import flight_options
from api.repositories import bookings, itinerary_items
from api.repositories.models import Booking
from api.sabre import client as sabre_client
from api.sabre import shapes

logger = logging.getLogger(__name__)

# Canned traveler for demo bookings — the demo trip has one traveler and the
# voice flow never collects passport-grade details.
_TRAVELER = shapes.TravelerRequest(givenName="Demo", surname="Traveler")
_CONTACT = shapes.ContactInfo(emails=["demo@example.com"], phones=["+16125550100"])


def _canned_ref(kind: str, item_id: str) -> str:
    """Deterministic confirmation ref for the non-Sabre category mocks."""
    digest = hashlib.sha256(f"{kind}|{item_id}".encode()).hexdigest().upper()
    return f"{kind[:3].upper()}-{digest[:8]}"


async def _write_booking(
    trip_id: str,
    item_id: str,
    sabre_ref: str,
    raw_response: dict,
) -> str:
    """The write path every tool shares: a bookings row with the provider
    payload. Raises on a failed write so the repair never reports ok when
    nothing landed. Status transitions are NOT written here — the cascade
    unit owns them (single-writer rule)."""
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
    return booking.booking_id


async def _flip_status(item_id: str, status: str) -> None:
    """Status write for the initial booking tool only — repairs never call
    this; their transitions belong to the cascade unit. Raises on a failed
    or 0-row write."""
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

    await _write_booking(trip_id, item_id, booked.confirmationId, booked.model_dump())
    await _flip_status(item_id, "booked")
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


def _pick_replacement(
    options: List[flight_options.FlightOption],
    cancelled_flight: Optional[Tuple[str, int]],
    original_arrive_time: Optional[str],
    original_depart_time: Optional[str] = None,
) -> flight_options.FlightOption:
    """Choose the replacement flight (Phase 29, decision 2; hardened by
    Phase 31 — live QA rebooked the traveler onto their cancelled flight):

    - Identity exclusion: drop any option whose (airline, flight_number) is
      the cancelled flight's. Since Phase 31 the voice booking stamps that
      identity into the item's details, so this filter actually engages.
    - No-identity fallback (seed trips, pre-Phase-31 rows): an option whose
      depart AND arrive clocks equal the original's is treated as the same
      flight and dropped.
    - Never fatal: if exclusion empties the pool, fall back to the
      unfiltered pool with a warning — a repaired-if-identical flight beats
      a crashed repair (the demo pins a pair with multiple itineraries).

    Among the survivors, return the option whose PT arrival is closest to
    the original flight's arrival time, protecting downstream hotel/ground
    timing. With no original arrival known, take the first option (response
    order — cheapest/earliest by the parser's contract). Assumes a
    non-empty list (the caller guarantees it via the mock fallback)."""
    candidates = options
    if cancelled_flight is not None:
        survivors = [
            o for o in options
            if (o.airline, o.flight_number) != cancelled_flight
        ]
    elif original_depart_time and original_arrive_time:
        survivors = [
            o for o in options
            if (o.depart_time[:5], o.arrive_time[:5])
            != (original_depart_time[:5], original_arrive_time[:5])
        ]
    else:
        survivors = options
    if survivors:
        candidates = survivors
    elif options:
        logger.warning(
            "flight repair: every candidate matches the cancelled flight; "
            "falling back to the unfiltered pool"
        )
    if not original_arrive_time:
        return candidates[0]
    target = _minutes_of_day(original_arrive_time)
    # Circular minute-of-day distance: the original arrival carries a PT
    # time-of-day but no date, so compare on the 24-hour clock (23:50 vs
    # 00:10 is 20 minutes apart, not 1420) — the honest closest-arrival read.
    return min(
        candidates,
        key=lambda o: _clock_distance(_minutes_of_day(o.arrive_time), target),
    )


def _minutes_of_day(hhmm: str) -> int:
    """'14:30' -> minutes since midnight."""
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def _clock_distance(a: int, b: int) -> int:
    """Shortest distance between two minute-of-day points on the 24h clock."""
    diff = abs(a - b)
    return min(diff, 1440 - diff)


async def _rebook_flight(
    trip_id: str,
    item_id: str,
    origin: str,
    destination: str,
    departure_date: str,
    original_price: float = 0.0,
    original_currency: str = "USD",
    original_arrive_time: Optional[str] = None,
    cancelled_flight: Optional[Tuple[str, int]] = None,
    original_depart_time: Optional[str] = None,
) -> dict:
    """Rebook a broken flight by re-shopping **real InstaFlights data**
    (Phase 29): the repair speaks a real replacement flight, not BFM content
    that has none on this PCC. Search the broken route/date, parse the priced
    itineraries, pick a real alternative, and cancel + create the PNR (the
    create stays the mock client — the entitlement wall is permanent). Writes
    an enriched `flight_repair` booking; the cascade unit owns the item's
    status flip.

    The original flight's context (price/currency/arrival/flight number) is
    supplied best-effort by the caller (sabre_tools._repair_call) for the
    selection and price-delta; every param is optional so the walkthrough
    endpoint and tests can omit it."""
    old_ref = await _latest_sabre_ref(trip_id, item_id)

    request = shapes.InstaFlightsRequest(
        origin=origin, destination=destination, departuredate=departure_date,
    )
    search = await sabre_client.instaflights_search(request)
    options = flight_options._parse_instaflights_options(search, origin, destination)

    # Empty -> mock fallback (decision 3): the dispatcher returns an honest
    # empty on the documented no-results 404 (Phase 28) rather than mock-
    # swapping, so a merely-empty cache date reaches here as zero options. Call
    # the mock directly for the same route/date so the 60-second cascade never
    # stalls, and log the route. When the real parse succeeded, this stays False.
    from_mock_fallback = False
    if not options:
        from_mock_fallback = True
        logger.warning(
            "flight repair re-shop empty for %s-%s %s; using mock",
            origin, destination, departure_date,
        )
        mock_search = await sabre_client._mock.instaflights_search(request)
        options = flight_options._parse_instaflights_options(
            mock_search, origin, destination
        )

    chosen = _pick_replacement(
        options, cancelled_flight, original_arrive_time, original_depart_time
    )

    # PNR write stays mock — permanently (requirements/DoD-C). Only the *search*
    # above is real; the cancel + create go straight to the mock client, never
    # the mode dispatcher. In real mode the dispatcher would attempt the real
    # cancel/create, and cancel is entitlement-*authorized* (only create is
    # blocked), so a real cancel could mutate the live CERT PNR before the create
    # failed into a mock fallback. Sourcing from the chosen real option's fields.
    rebooked = await sabre_client._mock.rebook_flight(
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
                            flightNumber=chosen.flight_number,
                            airlineCode=chosen.airline,
                            fromAirportCode=origin,
                            toAirportCode=destination,
                            departureDate=chosen.depart_date,
                            departureTime=chosen.depart_time,
                        )
                    ],
                    flightPricing=[shapes.FlightPricing()],
                ),
            ),
        )
    )

    # The original flight, structured, from the best-effort caller context
    # (Phase 32): the cascade page's old -> new treatment and the detail
    # payload's "was ..." line both speak from this block. Identity may be
    # absent (seed trips, walkthrough calls) — every field is optional.
    rebooked_from = {
        "airline": cancelled_flight[0] if cancelled_flight else None,
        "flight_number": cancelled_flight[1] if cancelled_flight else None,
        # Phase 33: the spoken/displayed name too, so the was-line can name
        # the old carrier without a code lookup at render time.
        "airline_name": (
            flight_options.airline_name(cancelled_flight[0])
            if cancelled_flight else None
        ),
        "depart_time": original_depart_time,
        "arrive_time": original_arrive_time,
        "price": original_price,
        "currency": original_currency,
    }

    # The enriched raw_response drives the booking page's flight_repair detail
    # panel (why-chosen / price-delta). The chosen option, the alternatives it
    # beat, the original fare, and the mock rebook payload (unchanged).
    raw_response = {
        "source": "flight_repair",
        "option": chosen.model_dump(),
        "alternatives": [o.model_dump() for o in options if o is not chosen],
        "original_price": original_price,
        "original_currency": original_currency,
        "rebooked_from": rebooked_from,
        "from_mock_fallback": from_mock_fallback,
        "rebooked": rebooked.model_dump(),
    }
    await _write_booking(
        trip_id, item_id, rebooked.created.confirmationId, raw_response
    )

    # Phase 32: write the rebooked flight into the itinerary_items row itself —
    # the cascade page renders exactly this row, so without this write the card
    # flips to `fixed` still showing the cancelled flight's times and price.
    # details.airline/flight_number become the NEW identity (the Phase 31
    # exclusion filter reads these keys — a second break -> repair must exclude
    # the flight the traveler is actually on now). Raising on a failed or 0-row
    # write keeps the ordering guarantee: _repair_one flips `fixed` only after
    # this tool returns, so the poll can never see `fixed` over stale fields.
    new_start_ts, new_end_ts = flight_options.option_timestamps(chosen)
    write_ok, affected_rows, write_error = await asyncio.to_thread(
        itinerary_items.update_flight_fields,
        item_id,
        start_ts=new_start_ts,
        end_ts=new_end_ts,
        price=chosen.price,
        currency=chosen.currency,
        # The shared stamp (Phase 33) keeps this write's key set identical
        # to the booking stamp's — this replace is wholesale, so a drifted
        # key set here silently strips fields from the card. rebooked_from
        # rides on top, repair-only.
        details={
            **flight_options.details_from_option(chosen),
            "rebooked_from": rebooked_from,
        },
    )
    if not write_ok:
        raise RuntimeError(
            f"flight field write failed for item {item_id}: {write_error}"
        )
    if affected_rows == 0:
        raise RuntimeError(
            f"flight field write for item {item_id} matched no rows"
        )

    return {
        "cancelled_ref": old_ref,
        "confirmation_ref": rebooked.created.confirmationId,
        "airline": chosen.airline,
        "flight_number": chosen.flight_number,
        "departure_date": chosen.depart_date,
        "departure_time": chosen.depart_time,
        "price": chosen.price,
        "currency": chosen.currency,
        "from_mock_fallback": from_mock_fallback,
        "price_delta": chosen.price - original_price,
    }


async def _shift_hotel_dates(
    trip_id: str,
    item_id: str,
    new_check_in: str,
    new_check_out: str,
) -> dict:
    """Move a hotel stay to new check-in/check-out dates via Sabre Modify
    Booking. Writes the updated booking; the cascade unit owns the item's
    status flip. Dates are YYYY-MM-DD."""
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

    await _write_booking(trip_id, item_id, modified.confirmationId, modified.model_dump())
    hotel = modified.booking.hotels[0]
    return {
        "confirmation_ref": modified.confirmationId,
        "hotel_name": hotel.hotelName,
        "check_in": hotel.checkInDate,
        "check_out": hotel.checkOutDate,
        "total": hotel.payment.total,
        "currency": hotel.payment.currencyCode,
    }


# --- Simple category mocks (no real provider this phase) ------------------------

async def _reschedule_ground(trip_id: str, item_id: str, new_pickup_time: str) -> dict:
    """Reschedule a ground transfer to a new pickup time. Canned mock — books
    the new pickup; the cascade unit owns the item's status flip."""
    ref = _canned_ref("ground", item_id)
    payload = {
        "provider": "mock-ground",
        "confirmation_ref": ref,
        "pickup_time": new_pickup_time,
        "vehicle": "standard sedan",
    }
    await _write_booking(trip_id, item_id, ref, payload)
    return {
        "confirmation_ref": ref,
        "pickup_time": new_pickup_time,
    }


async def _move_dining(trip_id: str, item_id: str, new_time: str) -> dict:
    """Move a dining reservation to a new time. Canned mock — rebooks the
    table; the cascade unit owns the item's status flip."""
    ref = _canned_ref("dining", item_id)
    payload = {
        "provider": "mock-dining",
        "confirmation_ref": ref,
        "reservation_time": new_time,
        "party_size": 2,
    }
    await _write_booking(trip_id, item_id, ref, payload)
    return {
        "confirmation_ref": ref,
        "reservation_time": new_time,
    }


async def _rebook_experience(trip_id: str, item_id: str, new_date: str) -> dict:
    """Rebook an experience/tour for a new date. Canned mock — issues new
    tickets; the cascade unit owns the item's status flip."""
    ref = _canned_ref("experience", item_id)
    payload = {
        "provider": "mock-experience",
        "confirmation_ref": ref,
        "date": new_date,
        "tickets": 2,
    }
    await _write_booking(trip_id, item_id, ref, payload)
    return {
        "confirmation_ref": ref,
        "date": new_date,
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
