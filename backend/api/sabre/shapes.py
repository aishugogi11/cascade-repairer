"""Pydantic models matching the documented Sabre payloads 1:1.

Source of truth: specs/2026-07-08-sabre-tools/sabre-api-notes.md (docs pull,
2026-07-08). Field names are Sabre's exact names — PascalCase for the OTA
flight-search payloads, camelCase for Booking Management — so a shape drift
between mock and documentation is a test failure. Payloads are trimmed to the
fields the notes file records; Sabre sends more, these are the ones we model.

Operations: flight search (Bargain Finder Max v5), flight book / hotel book
(Create Booking), flight cancel (Cancel Booking), flight rebook (composed
cancel + create — no single REST endpoint exists), hotel date change
(Modify Booking).
"""
from typing import List, Optional

from pydantic import BaseModel


# --- auth (POST /v2/auth/token) ------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str  # "bearer"
    expires_in: int  # seconds; 604800 (7 days) on CERT


# --- flight search: Bargain Finder Max v5 (POST /v5/offers/shop) ----------------
# Request root OTA_AirLowFareSearchRQ (PascalCase per OTA convention).

class CompanyName(BaseModel):
    Code: str  # "TN"


class RequestorID(BaseModel):
    Type: str
    ID: str
    CompanyName: CompanyName


class PosSource(BaseModel):
    PseudoCityCode: str
    RequestorID: RequestorID


class POS(BaseModel):
    Source: List[PosSource]


class AirportLocation(BaseModel):
    LocationCode: str  # IATA code, e.g. "MSP"


class OriginDestinationInformation(BaseModel):
    RPH: str
    DepartureDateTime: str  # "2026-07-17T08:00:00"
    OriginLocation: AirportLocation
    DestinationLocation: AirportLocation


class TravelPreferences(BaseModel):
    MaxStopsQuantity: Optional[int] = None


class PassengerTypeQuantity(BaseModel):
    Code: str  # "ADT"
    Quantity: int


class AirTravelerAvail(BaseModel):
    PassengerTypeQuantity: List[PassengerTypeQuantity]


class TravelerInfoSummary(BaseModel):
    AirTravelerAvail: List[AirTravelerAvail]


class RequestType(BaseModel):
    Name: str  # e.g. "50ITINS"


class IntelliSellTransaction(BaseModel):
    RequestType: RequestType


class TPAExtensions(BaseModel):
    IntelliSellTransaction: Optional[IntelliSellTransaction] = None


class OTAAirLowFareSearchRQ(BaseModel):
    Version: str = "5"
    POS: Optional[POS] = None
    OriginDestinationInformation: List[OriginDestinationInformation]
    TravelPreferences: Optional[TravelPreferences] = None
    TravelerInfoSummary: TravelerInfoSummary
    TPA_Extensions: Optional[TPAExtensions] = None


class FlightSearchRequest(BaseModel):
    OTA_AirLowFareSearchRQ: OTAAirLowFareSearchRQ


# Response root groupedItineraryResponse (GIR, camelCase). Itineraries
# reference legs by id (legs[].ref -> legDescs[].id); legs reference
# schedules (schedules[].ref -> scheduleDescs[].id).

class GirStatistics(BaseModel):
    itineraryCount: int


class ScheduleEndpoint(BaseModel):
    airport: str
    city: str
    country: str
    time: str  # "08:00:00-05:00"


class Equipment(BaseModel):
    code: str


class ScheduleCarrier(BaseModel):
    marketing: str
    marketingFlightNumber: int
    operating: str
    operatingFlightNumber: int
    equipment: Equipment


class ScheduleDesc(BaseModel):
    id: int
    stopCount: int
    eTicketable: bool
    elapsedTime: int  # minutes
    departure: ScheduleEndpoint
    arrival: ScheduleEndpoint
    carrier: ScheduleCarrier


class ScheduleRef(BaseModel):
    ref: int


class LegDesc(BaseModel):
    id: int
    elapsedTime: int
    schedules: List[ScheduleRef]


class LegDescription(BaseModel):
    departureDate: str
    departureLocation: str
    arrivalLocation: str


class GroupDescription(BaseModel):
    legDescriptions: List[LegDescription]


class LegRef(BaseModel):
    ref: int


class TotalFare(BaseModel):
    totalPrice: float
    currency: str
    baseFareAmount: float
    totalTaxAmount: float


class Fare(BaseModel):
    validatingCarrierCode: str
    totalFare: TotalFare


class PricingInformation(BaseModel):
    fare: Fare


class Itinerary(BaseModel):
    id: int
    legs: List[LegRef]
    pricingInformation: List[PricingInformation]


class ItineraryGroup(BaseModel):
    groupDescription: GroupDescription
    itineraries: List[Itinerary]


class GroupedItineraryResponse(BaseModel):
    version: str
    statistics: GirStatistics
    scheduleDescs: List[ScheduleDesc]
    legDescs: List[LegDesc]
    itineraryGroups: List[ItineraryGroup]


class FlightSearchResponse(BaseModel):
    groupedItineraryResponse: GroupedItineraryResponse


# --- Booking Management: Create Booking (POST /v1/trip/orders/createBooking) ----
# One unified service for air and hotel; flight book passes flightDetails,
# hotel book passes hotel (+ payment). camelCase per BM convention.

class TravelerRequest(BaseModel):
    givenName: str
    surname: str
    birthDate: Optional[str] = None  # "1980-01-01"
    passengerCode: str = "ADT"


class ContactInfo(BaseModel):
    emails: List[str]
    phones: List[str]


class FlightToBook(BaseModel):
    flightNumber: int
    airlineCode: str
    fromAirportCode: str
    toAirportCode: str
    departureDate: str  # "2026-07-17"
    departureTime: str  # "08:00"
    bookingClass: str = "Y"
    flightStatusCode: str = "NN"  # need/sell


class FlightPricing(BaseModel):
    """Empty object = price at booking with defaults."""


class FlightDetails(BaseModel):
    flights: List[FlightToBook]
    flightPricing: List[FlightPricing]


class HotelRoomRequest(BaseModel):
    travelerIndices: List[int]


class HotelToBook(BaseModel):
    useCsl: bool = True
    bookingKey: str  # UUID from POST /v5/hotel/pricecheck
    rooms: List[HotelRoomRequest]
    paymentPolicy: str = "GUARANTEE"  # GUARANTEE | DEPOSIT | LATE
    formOfPayment: int = 1  # 1-based index into payment.formsOfPayment


class FormOfPayment(BaseModel):
    type: str  # "PAYMENTCARD"
    cardTypeCode: str
    cardNumber: str
    expiryDate: str  # "2027-10"


class Payment(BaseModel):
    formsOfPayment: List[FormOfPayment]


class CreateBookingRequest(BaseModel):
    travelers: List[TravelerRequest]
    contactInfo: ContactInfo
    flightDetails: Optional[FlightDetails] = None  # flight book
    hotel: Optional[HotelToBook] = None  # hotel book
    payment: Optional[Payment] = None


# Response wrapper: timestamp + confirmationId + booking, where booking has
# the Get Booking structure. Top-level confirmationId is the Sabre PNR;
# flights[].confirmationId is the airline record locator; hotels[]./flights[]
# itemId is what cancel/modify calls target.

class BookedTraveler(BaseModel):
    givenName: str
    surname: str
    type: str  # "ADULT"
    passengerCode: str
    nameAssociationId: str


class BookedFlight(BaseModel):
    itemId: str
    confirmationId: str  # airline record locator
    flightNumber: int
    airlineCode: str
    fromAirportCode: str
    toAirportCode: str
    departureDate: str
    departureTime: str
    cabinTypeName: str
    flightStatusName: str  # "Confirmed"


class RoomRate(BaseModel):
    amount: str  # Sabre sends money as strings, e.g. "179.00"
    currencyCode: str


class BookedRoom(BaseModel):
    roomType: str
    quantity: int
    productCode: str
    roomRate: RoomRate
    travelerIndices: List[int]


class HotelPaymentTotal(BaseModel):
    subtotal: str
    taxes: str
    fees: Optional[str] = None
    total: str
    currencyCode: str


class BookedHotel(BaseModel):
    itemId: str
    confirmationId: str  # hotel supplier confirmation number
    hotelName: str
    checkInDate: str
    checkOutDate: str
    leadTravelerIndex: int
    room: BookedRoom
    isRefundable: bool
    hotelStatusCode: str  # "HK" = confirmed
    hotelStatusName: str
    chainCode: str
    propertyId: str
    paymentPolicy: str
    payment: HotelPaymentTotal
    numberOfGuests: int


class FlightPaymentTotal(BaseModel):
    subtotal: str
    taxes: str
    total: str
    currencyCode: str


class BookingPayments(BaseModel):
    flightTotals: Optional[List[FlightPaymentTotal]] = None
    hotelTotals: Optional[List[HotelPaymentTotal]] = None


class BookingDetails(BaseModel):
    """The Get Booking structure shared by create/cancel/modify responses."""

    bookingId: str  # same value as the wrapper's confirmationId
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    isCancelable: Optional[bool] = None
    isTicketed: Optional[bool] = None
    travelers: List[BookedTraveler] = []
    flights: Optional[List[BookedFlight]] = None
    hotels: Optional[List[BookedHotel]] = None
    payments: Optional[BookingPayments] = None


class CreateBookingResponse(BaseModel):
    timestamp: str
    confirmationId: str  # Sabre record locator (PNR)
    booking: BookingDetails


# --- flight cancel: Cancel Booking (POST /v1/trip/orders/cancelBooking) --------

class FlightItemRef(BaseModel):
    itemId: str


class CancelBookingRequest(BaseModel):
    confirmationId: str
    retrieveBooking: bool = True
    cancelAll: bool = False
    flights: Optional[List[FlightItemRef]] = None  # selective cancel by itemId
    errorHandlingPolicy: str = "HALT_ON_ERROR"  # or ALLOW_PARTIAL_CANCEL


class CancelBookingResponse(BaseModel):
    timestamp: str
    booking: BookingDetails  # post-cancel state (cancelled segments removed)


# --- flight rebook: composed cancel + create ------------------------------------
# No single REST endpoint exists (Modify Booking does not change flight
# segments; the exchange path needs tickets). For the demo's unticketed
# bookings the documented path is getBooking -> cancelBooking -> createBooking,
# so the rebook result carries both halves.

class RebookFlightRequest(BaseModel):
    confirmationId: str  # the booking whose flight is being replaced
    cancel: CancelBookingRequest
    create: CreateBookingRequest


class RebookFlightResponse(BaseModel):
    cancelled: CancelBookingResponse
    created: CreateBookingResponse  # the new booking; its confirmationId is the new PNR


# --- hotel date change: Modify Booking (POST /v1/trip/orders/modifyBooking) ----
# bookingSignature comes from a fresh getBooking call (optimistic locking).
# Dates outside the originally shopped range additionally need a re-shopped
# bookingKey inside the after.hotels[] item.

class HotelAfterState(BaseModel):
    itemId: str
    checkInDate: str
    checkOutDate: str
    leadTravelerIndex: int = 1
    paymentPolicy: str = "GUARANTEE"
    room: HotelRoomRequest
    numberOfGuests: int = 1
    bookingKey: Optional[str] = None  # only when re-shopped (out-of-range dates)


class ModifyAfterState(BaseModel):
    hotels: List[HotelAfterState]
    travelers: List[TravelerRequest]


class ModifyBookingRequest(BaseModel):
    bookingSignature: str
    confirmationId: str
    before: dict = {}  # Sabre's own date-change samples send an empty before
    after: ModifyAfterState
    retrieveBooking: bool = True
    receivedFrom: str = "API"


class ModifyBookingResponse(BaseModel):
    timestamp: str
    confirmationId: str
    booking: BookingDetails  # updated state, new checkIn/checkOut dates


# --- flight search: InstaFlights (GET /v1/shop/flights) -------------------------
# Source of truth: specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md
# (verified-live 2026-07-13, delta #5). The entitled search API on the
# hackathon PCC — BFM v5 above stays untouched (Phase 24 punch list). Request
# is a query-param bag, not a JSON body; the response models only the fields
# the concierge parser needs (Sabre sends far more — extras are tolerated by
# pydantic's default ignore). DepartureDateTime/ArrivalDateTime carry NO UTC
# offset: they are airport-local wall clock ("2026-08-13T07:20:00" = 7:20 AM
# at that airport) and must be converted before speaking/storing.


class InstaFlightsRequest(BaseModel):
    """Query params for GET /v1/shop/flights. onlineitinerariesonly must
    reach CERT as N — Y triggers a server-side 500 (verified-live); the real
    client enforces N regardless of this field's value."""

    origin: str  # IATA, e.g. "SFO"
    destination: str
    departuredate: str  # YYYY-MM-DD
    onlineitinerariesonly: str = "N"
    limit: int = 10


class MarketingAirline(BaseModel):
    Code: str  # "DL"


class SegmentAirport(BaseModel):
    LocationCode: str  # IATA code


class FlightSegment(BaseModel):
    DepartureAirport: SegmentAirport
    ArrivalAirport: SegmentAirport
    DepartureDateTime: str  # "2026-08-13T07:20:00" — airport-local, no offset
    ArrivalDateTime: str  # same convention
    FlightNumber: int
    MarketingAirline: MarketingAirline
    StopQuantity: int = 0


class OriginDestinationOption(BaseModel):
    FlightSegment: List[FlightSegment]
    # Whole-journey minutes including layovers (Phase 33). Optional: a real
    # itinerary missing it must still parse — rich fields degrade, never skip.
    ElapsedTime: Optional[int] = None


class OriginDestinationOptions(BaseModel):
    OriginDestinationOption: List[OriginDestinationOption]


class AirItinerary(BaseModel):
    OriginDestinationOptions: OriginDestinationOptions


class InstaTotalFare(BaseModel):
    Amount: float  # Sabre sends money as strings ("260.60"); pydantic coerces
    CurrencyCode: str


class ItinTotalFare(BaseModel):
    TotalFare: InstaTotalFare


class CabinInfo(BaseModel):
    Cabin: str  # booking-class letter, e.g. "Y"


class FareInfoTPAExtensions(BaseModel):
    Cabin: Optional[CabinInfo] = None


class InstaFareInfo(BaseModel):
    TPA_Extensions: Optional[FareInfoTPAExtensions] = None


class InstaFareInfos(BaseModel):
    FareInfo: List[InstaFareInfo] = []


class AirItineraryPricingInfo(BaseModel):
    ItinTotalFare: ItinTotalFare
    # Cabin chain (Phase 33): FareInfos.FareInfo[0].TPA_Extensions.Cabin.Cabin
    # per the notebook's observed response. Optional end to end.
    FareInfos: Optional[InstaFareInfos] = None


class PricedItinerary(BaseModel):
    AirItinerary: AirItinerary
    AirItineraryPricingInfo: AirItineraryPricingInfo


class InstaFlightsResponse(BaseModel):
    PricedItineraries: List[PricedItinerary]


# --- supported markets (GET /v1/lists/supported/shop/flights/origins-destinations)
# The city-pair list InstaFlights carries — minimal fields for a membership
# check (verified-live 2026-07-13; the sweep probed with ?destinationcountry=US).


class MarketLocation(BaseModel):
    AirportCode: str


class OriginDestinationLocation(BaseModel):
    OriginLocation: MarketLocation
    DestinationLocation: MarketLocation


class SupportedMarketsResponse(BaseModel):
    OriginDestinationLocations: List[OriginDestinationLocation] = []
