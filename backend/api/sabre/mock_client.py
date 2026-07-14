"""Mock Sabre client — canned responses in the documented shapes.

Every return value is a shapes.py model instance, so a drift between mock
and documentation is a validation error, not a demo-day surprise.
Deterministic given the same request: refs and ids are derived from request
fields by hashing, never random. `latency_seconds` adds a small artificial
delay (network feel for the demo); tests pass 0.
"""
import asyncio
import hashlib

from api.sabre import shapes


def _ref(*parts: str, length: int = 6) -> str:
    """Deterministic uppercase pseudo-locator from the request fields."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest().upper()
    # Letters only, so it reads like a Sabre PNR.
    letters = [c for c in digest if c.isalpha()]
    return "".join(letters[:length]).ljust(length, "X")


_TIMESTAMP = "2026-07-08T00:00:00"  # fixed: deterministic, and clearly canned


class MockSabreClient:
    """Same interface as RealSabreClient; returns documented shapes."""

    def __init__(self, latency_seconds: float = 0.2):
        self.latency_seconds = latency_seconds

    async def _lag(self) -> None:
        if self.latency_seconds:
            await asyncio.sleep(self.latency_seconds)

    # Three deterministic variants per search (BFM returns many; the guided
    # voice booking needs 2–3 speakable choices). The first stays the
    # original 8 AM nonstop so callers that pick [0] behave exactly as
    # before: (depart, arrive, stops, elapsed_minutes, price_delta).
    _FLIGHT_VARIANTS = [
        ("08:00:00-05:00", "10:05:00-07:00", 0, 245, 0.0),
        ("11:30:00-05:00", "13:40:00-07:00", 0, 250, 54.4),
        ("06:15:00-05:00", "11:20:00-07:00", 1, 425, -32.6),
    ]

    async def flight_search(
        self, request: shapes.FlightSearchRequest
    ) -> shapes.FlightSearchResponse:
        """Bargain Finder Max v5 — three itineraries per leg searched."""
        await self._lag()
        od = request.OTA_AirLowFareSearchRQ.OriginDestinationInformation[0]
        origin = od.OriginLocation.LocationCode
        dest = od.DestinationLocation.LocationCode
        flight_number = int(hashlib.sha256(f"{origin}{dest}".encode()).hexdigest(), 16) % 900 + 100
        schedule_descs, leg_descs, itineraries = [], [], []
        for i, (depart, arrive, stops, elapsed, delta) in enumerate(
            self._FLIGHT_VARIANTS, start=1
        ):
            schedule_descs.append(
                shapes.ScheduleDesc(
                    id=i,
                    stopCount=stops,
                    eTicketable=True,
                    elapsedTime=elapsed,
                    departure=shapes.ScheduleEndpoint(
                        airport=origin, city=origin, country="US", time=depart,
                    ),
                    arrival=shapes.ScheduleEndpoint(
                        airport=dest, city=dest, country="US", time=arrive,
                    ),
                    carrier=shapes.ScheduleCarrier(
                        marketing="AA",
                        marketingFlightNumber=flight_number + (i - 1) * 7,
                        operating="AA",
                        operatingFlightNumber=flight_number + (i - 1) * 7,
                        equipment=shapes.Equipment(code="E75"),
                    ),
                )
            )
            leg_descs.append(
                shapes.LegDesc(
                    id=i, elapsedTime=elapsed,
                    schedules=[shapes.ScheduleRef(ref=i)],
                )
            )
            itineraries.append(
                shapes.Itinerary(
                    id=i,
                    legs=[shapes.LegRef(ref=i)],
                    pricingInformation=[
                        shapes.PricingInformation(
                            fare=shapes.Fare(
                                validatingCarrierCode="AA",
                                totalFare=shapes.TotalFare(
                                    totalPrice=round(187.6 + delta, 2),
                                    currency="USD",
                                    baseFareAmount=round(143.0 + delta, 2),
                                    totalTaxAmount=44.6,
                                ),
                            )
                        )
                    ],
                )
            )
        return shapes.FlightSearchResponse(
            groupedItineraryResponse=shapes.GroupedItineraryResponse(
                version="5",
                statistics=shapes.GirStatistics(itineraryCount=len(itineraries)),
                scheduleDescs=schedule_descs,
                legDescs=leg_descs,
                itineraryGroups=[
                    shapes.ItineraryGroup(
                        groupDescription=shapes.GroupDescription(
                            legDescriptions=[
                                shapes.LegDescription(
                                    departureDate=od.DepartureDateTime[:10],
                                    departureLocation=origin,
                                    arrivalLocation=dest,
                                )
                            ]
                        ),
                        itineraries=itineraries,
                    )
                ],
            )
        )

    # Same semantic spread as the BFM variants above — nonstop/one-stop,
    # morning/midday, matching price points — so the guided-booking flow in
    # SABRE_MODE=mock behaves as before in spirit. Times keep the mock's
    # Pacific wall-clock fiction, expressed in the InstaFlights offset-less
    # airport-local convention: (depart, arrive, stops, price).
    _INSTA_VARIANTS = [
        ("08:00:00", "10:05:00", 0, 187.6),
        ("11:30:00", "13:40:00", 0, 242.0),
        ("06:15:00", "11:20:00", 1, 155.0),
    ]

    async def instaflights_search(
        self, request: shapes.InstaFlightsRequest
    ) -> shapes.InstaFlightsResponse:
        """InstaFlights — three deterministic priced itineraries."""
        await self._lag()
        origin = request.origin.upper()
        dest = request.destination.upper()
        day = request.departuredate
        flight_number = int(hashlib.sha256(f"{origin}{dest}".encode()).hexdigest(), 16) % 900 + 100
        itineraries = []
        for i, (depart, arrive, stops, price) in enumerate(self._INSTA_VARIANTS):
            itineraries.append(
                shapes.PricedItinerary(
                    AirItinerary=shapes.AirItinerary(
                        OriginDestinationOptions=shapes.OriginDestinationOptions(
                            OriginDestinationOption=[
                                shapes.OriginDestinationOption(
                                    FlightSegment=[
                                        shapes.FlightSegment(
                                            DepartureAirport=shapes.SegmentAirport(
                                                LocationCode=origin
                                            ),
                                            ArrivalAirport=shapes.SegmentAirport(
                                                LocationCode=dest
                                            ),
                                            DepartureDateTime=f"{day}T{depart}",
                                            ArrivalDateTime=f"{day}T{arrive}",
                                            FlightNumber=flight_number + i * 7,
                                            MarketingAirline=shapes.MarketingAirline(
                                                Code="AA"
                                            ),
                                            StopQuantity=stops,
                                        )
                                    ]
                                )
                            ]
                        )
                    ),
                    AirItineraryPricingInfo=shapes.AirItineraryPricingInfo(
                        ItinTotalFare=shapes.ItinTotalFare(
                            TotalFare=shapes.InstaTotalFare(
                                Amount=price, CurrencyCode="USD"
                            )
                        )
                    ),
                )
            )
        return shapes.InstaFlightsResponse(PricedItineraries=itineraries)

    async def create_booking(
        self, request: shapes.CreateBookingRequest
    ) -> shapes.CreateBookingResponse:
        """Create Booking — flight and/or hotel, per the request elements."""
        await self._lag()
        traveler = request.travelers[0]
        pnr = _ref("pnr", traveler.surname, str(request.model_dump()))
        booked_travelers = [
            shapes.BookedTraveler(
                givenName=t.givenName.upper(),
                surname=t.surname.upper(),
                type="ADULT",
                passengerCode=t.passengerCode,
                nameAssociationId=str(i + 1),
            )
            for i, t in enumerate(request.travelers)
        ]

        flights = None
        flight_totals = None
        if request.flightDetails is not None:
            flights = [
                shapes.BookedFlight(
                    itemId=str(12 + i),
                    confirmationId=_ref("air", f.airlineCode, str(f.flightNumber)),
                    flightNumber=f.flightNumber,
                    airlineCode=f.airlineCode,
                    fromAirportCode=f.fromAirportCode,
                    toAirportCode=f.toAirportCode,
                    departureDate=f.departureDate,
                    departureTime=f.departureTime,
                    cabinTypeName="ECONOMY",
                    flightStatusName="Confirmed",
                )
                for i, f in enumerate(request.flightDetails.flights)
            ]
            flight_totals = [
                shapes.FlightPaymentTotal(
                    subtotal="143.00", taxes="44.60", total="187.60",
                    currencyCode="USD",
                )
            ]

        hotels = None
        hotel_totals = None
        if request.hotel is not None:
            hotels = [
                shapes.BookedHotel(
                    itemId="32",
                    confirmationId=_ref("htl", request.hotel.bookingKey, length=10),
                    hotelName="TRU BY HILTON MOUNTAIN VIEW",
                    checkInDate="2026-07-17",
                    checkOutDate="2026-07-19",
                    leadTravelerIndex=1,
                    room=shapes.BookedRoom(
                        roomType="Guest Room",
                        quantity=1,
                        productCode="A05LV0",
                        roomRate=shapes.RoomRate(amount="179.00", currencyCode="USD"),
                        travelerIndices=request.hotel.rooms[0].travelerIndices,
                    ),
                    isRefundable=True,
                    hotelStatusCode="HK",
                    hotelStatusName="Confirmed",
                    chainCode="RU",
                    propertyId="102114737",
                    paymentPolicy=request.hotel.paymentPolicy,
                    payment=shapes.HotelPaymentTotal(
                        subtotal="365.16", taxes="60.86", fees="7.16",
                        total="426.02", currencyCode="USD",
                    ),
                    numberOfGuests=len(request.hotel.rooms[0].travelerIndices),
                )
            ]
            hotel_totals = [
                shapes.HotelPaymentTotal(
                    subtotal="365.16", taxes="60.86", fees="7.16",
                    total="426.02", currencyCode="USD",
                )
            ]

        return shapes.CreateBookingResponse(
            timestamp=_TIMESTAMP,
            confirmationId=pnr,
            booking=shapes.BookingDetails(
                bookingId=pnr,
                startDate="2026-07-17",
                endDate="2026-07-19",
                isCancelable=True,
                isTicketed=False,
                travelers=booked_travelers,
                flights=flights,
                hotels=hotels,
                payments=shapes.BookingPayments(
                    flightTotals=flight_totals, hotelTotals=hotel_totals
                ),
            ),
        )

    async def cancel_booking(
        self, request: shapes.CancelBookingRequest
    ) -> shapes.CancelBookingResponse:
        """Cancel Booking — post-cancel state, cancelled segments removed."""
        await self._lag()
        return shapes.CancelBookingResponse(
            timestamp=_TIMESTAMP,
            booking=shapes.BookingDetails(
                bookingId=request.confirmationId,
                travelers=[
                    shapes.BookedTraveler(
                        givenName="JOSH", surname="JANZEN", type="ADULT",
                        passengerCode="ADT", nameAssociationId="1",
                    )
                ],
                flights=[] if not request.cancelAll else None,
            ),
        )

    async def rebook_flight(
        self, request: shapes.RebookFlightRequest
    ) -> shapes.RebookFlightResponse:
        """Rebook = cancel + create, composed (no single REST endpoint)."""
        cancelled = await self.cancel_booking(request.cancel)
        created = await self.create_booking(request.create)
        return shapes.RebookFlightResponse(cancelled=cancelled, created=created)

    async def modify_booking(
        self, request: shapes.ModifyBookingRequest
    ) -> shapes.ModifyBookingResponse:
        """Modify Booking — hotel date change; echoes the requested dates."""
        await self._lag()
        after = request.after.hotels[0]
        return shapes.ModifyBookingResponse(
            timestamp=_TIMESTAMP,
            confirmationId=request.confirmationId,
            booking=shapes.BookingDetails(
                bookingId=request.confirmationId,
                startDate=after.checkInDate,
                endDate=after.checkOutDate,
                isCancelable=True,
                isTicketed=False,
                travelers=[
                    shapes.BookedTraveler(
                        givenName=t.givenName.upper(),
                        surname=t.surname.upper(),
                        type="ADULT",
                        passengerCode=t.passengerCode,
                        nameAssociationId=str(i + 1),
                    )
                    for i, t in enumerate(request.after.travelers)
                ],
                hotels=[
                    shapes.BookedHotel(
                        itemId=after.itemId,
                        confirmationId=_ref("htl", request.confirmationId, length=10),
                        hotelName="TRU BY HILTON MOUNTAIN VIEW",
                        checkInDate=after.checkInDate,
                        checkOutDate=after.checkOutDate,
                        leadTravelerIndex=after.leadTravelerIndex,
                        room=shapes.BookedRoom(
                            roomType="Guest Room",
                            quantity=1,
                            productCode="A05LV0",
                            roomRate=shapes.RoomRate(amount="179.00", currencyCode="USD"),
                            travelerIndices=after.room.travelerIndices,
                        ),
                        isRefundable=True,
                        hotelStatusCode="HK",
                        hotelStatusName="Confirmed",
                        chainCode="RU",
                        propertyId="102114737",
                        paymentPolicy=after.paymentPolicy,
                        payment=shapes.HotelPaymentTotal(
                            subtotal="365.16", taxes="60.86", fees="7.16",
                            total="426.02", currencyCode="USD",
                        ),
                        numberOfGuests=after.numberOfGuests,
                    )
                ],
            ),
        )
