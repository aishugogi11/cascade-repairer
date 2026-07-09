"""Sabre client layer tests — hermetic: no network, no credentials.

Shape fidelity: every mock response is (and validates as) the shapes.py model
built from sabre-api-notes.md. Dispatch: SABRE_MODE is read per call.
Fallback: a raising real client yields the mock result plus a logged warning
naming the operation.

The repo pins no pytest-asyncio, so async scenarios run via asyncio.run()
inside sync tests.
"""
import asyncio
import logging

import pytest

from api.sabre import client, shapes
from api.sabre.mock_client import MockSabreClient
from api.sabre.real_client import RealSabreClient, SabreNotConfiguredError


def search_request(origin="MSP", dest="SFO"):
    return shapes.FlightSearchRequest(
        OTA_AirLowFareSearchRQ=shapes.OTAAirLowFareSearchRQ(
            OriginDestinationInformation=[
                shapes.OriginDestinationInformation(
                    RPH="1",
                    DepartureDateTime="2026-07-17T08:00:00",
                    OriginLocation=shapes.AirportLocation(LocationCode=origin),
                    DestinationLocation=shapes.AirportLocation(LocationCode=dest),
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


def flight_booking_request():
    return shapes.CreateBookingRequest(
        travelers=[shapes.TravelerRequest(givenName="Josh", surname="Janzen")],
        contactInfo=shapes.ContactInfo(
            emails=["demo@example.com"], phones=["+16125550100"]
        ),
        flightDetails=shapes.FlightDetails(
            flights=[
                shapes.FlightToBook(
                    flightNumber=576,
                    airlineCode="AA",
                    fromAirportCode="MSP",
                    toAirportCode="SFO",
                    departureDate="2026-07-17",
                    departureTime="08:00",
                )
            ],
            flightPricing=[shapes.FlightPricing()],
        ),
    )


def hotel_booking_request():
    return shapes.CreateBookingRequest(
        travelers=[shapes.TravelerRequest(givenName="Josh", surname="Janzen")],
        contactInfo=shapes.ContactInfo(
            emails=["demo@example.com"], phones=["+16125550100"]
        ),
        hotel=shapes.HotelToBook(
            bookingKey="6f0a79e3-2fb4-4305-92c7-00f138ed29a9",
            rooms=[shapes.HotelRoomRequest(travelerIndices=[1])],
        ),
        payment=shapes.Payment(
            formsOfPayment=[
                shapes.FormOfPayment(
                    type="PAYMENTCARD",
                    cardTypeCode="VI",
                    cardNumber="4111111111111111",
                    expiryDate="2027-10",
                )
            ]
        ),
    )


def cancel_request():
    return shapes.CancelBookingRequest(confirmationId="GLEBNY", cancelAll=True)


def rebook_request():
    return shapes.RebookFlightRequest(
        confirmationId="GLEBNY",
        cancel=shapes.CancelBookingRequest(
            confirmationId="GLEBNY",
            flights=[shapes.FlightItemRef(itemId="12")],
        ),
        create=flight_booking_request(),
    )


def modify_request():
    return shapes.ModifyBookingRequest(
        bookingSignature="d64eb4d0efb0043e",
        confirmationId="UEEBMH",
        after=shapes.ModifyAfterState(
            hotels=[
                shapes.HotelAfterState(
                    itemId="32",
                    checkInDate="2026-07-18",
                    checkOutDate="2026-07-20",
                    room=shapes.HotelRoomRequest(travelerIndices=[1]),
                )
            ],
            travelers=[shapes.TravelerRequest(givenName="Josh", surname="Janzen")],
        ),
    )


@pytest.fixture
def mock():
    return MockSabreClient(latency_seconds=0)


@pytest.fixture(autouse=True)
def zero_mock_latency(monkeypatch):
    """The dispatcher's module-level mock keeps demo latency; tests skip it."""
    monkeypatch.setattr(client._mock, "latency_seconds", 0)


# --- shape fidelity: every documented operation returns its shapes.py model ----

OPERATIONS = [
    ("flight_search", search_request, shapes.FlightSearchResponse),
    ("create_booking", flight_booking_request, shapes.CreateBookingResponse),
    ("cancel_booking", cancel_request, shapes.CancelBookingResponse),
    ("rebook_flight", rebook_request, shapes.RebookFlightResponse),
    ("modify_booking", modify_request, shapes.ModifyBookingResponse),
]


@pytest.mark.parametrize("operation,make_request,response_model", OPERATIONS)
def test_mock_response_validates_against_documented_shape(
    mock, operation, make_request, response_model
):
    response = asyncio.run(getattr(mock, operation)(make_request()))
    assert isinstance(response, response_model)
    # Round-trip through plain dicts: the payload itself validates, not just
    # the instance type.
    response_model.model_validate(response.model_dump())


def test_hotel_booking_covers_the_documented_hotel_shape(mock):
    """Hotel book shares create_booking; assert the hotel side of the shape."""
    response = asyncio.run(mock.create_booking(hotel_booking_request()))
    hotel = response.booking.hotels[0]
    assert hotel.hotelStatusCode == "HK"
    assert hotel.itemId == "32"
    assert response.confirmationId == response.booking.bookingId
    shapes.CreateBookingResponse.model_validate(response.model_dump())


def test_mock_is_deterministic_for_the_same_request(mock):
    a = asyncio.run(mock.create_booking(flight_booking_request()))
    b = asyncio.run(mock.create_booking(flight_booking_request()))
    assert a == b

    s1 = asyncio.run(mock.flight_search(search_request()))
    s2 = asyncio.run(mock.flight_search(search_request()))
    assert s1 == s2
    # Different request -> different flight, so responses trace to requests.
    s3 = asyncio.run(mock.flight_search(search_request(origin="JFK")))
    assert s1 != s3


def test_rebook_returns_a_new_pnr_and_the_cancelled_booking(mock):
    response = asyncio.run(mock.rebook_flight(rebook_request()))
    assert response.cancelled.booking.bookingId == "GLEBNY"
    assert response.created.confirmationId  # the new PNR
    assert response.created.booking.flights[0].flightStatusName == "Confirmed"


def test_modify_booking_echoes_the_new_dates(mock):
    response = asyncio.run(mock.modify_booking(modify_request()))
    hotel = response.booking.hotels[0]
    assert (hotel.checkInDate, hotel.checkOutDate) == ("2026-07-18", "2026-07-20")


# --- dispatcher: SABRE_MODE read per call ---------------------------------------

def test_dispatcher_defaults_to_mock_when_unset(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)

    async def never(request):
        raise AssertionError("real client must not be touched in mock mode")

    monkeypatch.setattr(client._real, "cancel_booking", never)
    response = asyncio.run(client.cancel_booking(cancel_request()))
    assert isinstance(response, shapes.CancelBookingResponse)


def test_dispatcher_mock_mode_never_touches_the_real_client(monkeypatch, caplog):
    monkeypatch.setenv("SABRE_MODE", "mock")

    async def never(request):
        raise AssertionError("real client must not be touched in mock mode")

    monkeypatch.setattr(client._real, "flight_search", never)
    with caplog.at_level(logging.WARNING):
        response = asyncio.run(client.flight_search(search_request()))
    assert isinstance(response, shapes.FlightSearchResponse)
    assert "falling back" not in caplog.text  # served by the mock directly


def test_dispatcher_reads_the_flag_per_call(monkeypatch, caplog):
    """Flip the env mid-test: mock -> real (unconfigured, so it falls back,
    proving the real path was actually taken) -> mock again."""
    async def scenario():
        monkeypatch.setenv("SABRE_MODE", "mock")
        first = await client.cancel_booking(cancel_request())

        monkeypatch.setenv("SABRE_MODE", "real")
        with caplog.at_level(logging.WARNING):
            second = await client.cancel_booking(cancel_request())

        monkeypatch.setenv("SABRE_MODE", "mock")
        third = await client.cancel_booking(cancel_request())
        return first, second, third

    first, second, third = asyncio.run(scenario())
    assert first == second == third  # all mock results in the end
    assert "cancel_booking" in caplog.text  # but the real path ran mid-test
    assert client.sabre_mode() == "mock"


# --- auto-fallback: real-mode failure yields the mock result + a warning --------

def test_real_mode_failure_falls_back_to_mock_and_logs(monkeypatch, caplog):
    monkeypatch.setenv("SABRE_MODE", "real")

    async def boom(request):
        raise RuntimeError("sandbox flaked")

    monkeypatch.setattr(client._real, "create_booking", boom)

    with caplog.at_level(logging.WARNING):
        response = asyncio.run(client.create_booking(flight_booking_request()))

    assert isinstance(response, shapes.CreateBookingResponse)  # the mock result
    expected = asyncio.run(client._mock.create_booking(flight_booking_request()))
    assert response == expected

    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    assert "create_booking" in warning.getMessage()
    assert "sandbox flaked" in warning.getMessage()
    assert "falling back" in warning.getMessage()


def test_real_mode_without_config_falls_back_via_clear_error(monkeypatch, caplog):
    """No SABRE_BASE_URL/SABRE_CLIENT_SECRET set: the real client raises its
    configuration error, and the dispatcher still serves the mock."""
    monkeypatch.setenv("SABRE_MODE", "real")
    monkeypatch.delenv("SABRE_BASE_URL", raising=False)
    monkeypatch.delenv("SABRE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(client, "_real", RealSabreClient())  # re-read the env

    with caplog.at_level(logging.WARNING):
        response = asyncio.run(client.flight_search(search_request()))

    assert isinstance(response, shapes.FlightSearchResponse)
    assert "SabreNotConfiguredError" in caplog.text
    assert "flight_search" in caplog.text


def test_real_client_unconfigured_raises_a_clear_error(monkeypatch):
    monkeypatch.delenv("SABRE_BASE_URL", raising=False)
    monkeypatch.delenv("SABRE_CLIENT_SECRET", raising=False)
    real = RealSabreClient()
    with pytest.raises(SabreNotConfiguredError, match="SABRE_BASE_URL"):
        asyncio.run(real.flight_search(search_request()))
