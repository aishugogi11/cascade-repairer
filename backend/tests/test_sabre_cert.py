"""Live Sabre CERT certification of the UNMODIFIED real client (Phase 25).

Deselected by default (pytest.ini addopts `-m "not cert"`) — CI and local
runs stay hermetic. Run deliberately, inside the container, with the raw
credential pair from config/.env:

    set -a && . ./config/.env && set +a && \
    docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET backend \
        python -m pytest -m cert tests/test_sabre_cert.py -v

These tests certify what CERT *actually does* with the hackathon credentials
(explored 2026-07-13 — see specs/2026-07-13-sabre-cert-exploration/
sabre-cert-notes.md). Several assert documented entitlement gaps as
tripwires: if Sabre widens entitlements (or resets credentials), the failing
test names exactly what changed. Every path that could create a PNR cancels
it in a finally block.

The repo pins no pytest-asyncio, so async scenarios run via asyncio.run()
inside sync tests (the test_sabre_client.py convention).
"""
import asyncio
import base64
import os

import pytest
from pydantic import ValidationError

from api.sabre import shapes
from api.sabre.real_client import RealSabreClient

pytestmark = [
    pytest.mark.cert,
    pytest.mark.skipif(
        not (os.environ.get("SABRE_API_USER_ID") and os.environ.get("SABRE_API_SECRET")),
        reason="cert tests need SABRE_API_USER_ID + SABRE_API_SECRET (config/.env)",
    ),
]

CERT_BASE_URL = "https://api.cert.platform.sabre.com"


def _build_secret(user_id: str, password: str) -> str:
    """The documented v2 Basic-secret recipe (verified live 2026-07-13)."""
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    return b64(f"{b64(user_id)}:{b64(password)}")


@pytest.fixture(autouse=True)
def bridge_env(monkeypatch):
    """The Phase 24 env bridge: derive the client's expected env vars from
    the raw pair, without modifying the client."""
    monkeypatch.setenv("SABRE_BASE_URL", CERT_BASE_URL)
    monkeypatch.setenv(
        "SABRE_CLIENT_SECRET",
        _build_secret(os.environ["SABRE_API_USER_ID"], os.environ["SABRE_API_SECRET"]),
    )


@pytest.fixture()
def client(bridge_env) -> RealSabreClient:
    return RealSabreClient()


def _pos_dict() -> dict:
    """The POS block CERT requires, as a raw dict — the shapes model cannot
    carry it (see test_shapes_pos_field_is_dead)."""
    pcc = os.environ["SABRE_API_USER_ID"].split(":")[2]
    return {
        "Source": [
            {
                "PseudoCityCode": pcc,
                "RequestorID": {
                    "Type": "1",
                    "ID": "1",
                    "CompanyName": {"Code": "TN"},
                },
            }
        ]
    }


def _search_request_without_pos() -> shapes.FlightSearchRequest:
    """The best request the shapes model can express: no POS (dead field),
    no IntelliSell RequestType (e.g. 50ITINS triggers 'PROCESSING ERROR
    DETECTED' on these credentials — probed 2026-07-13)."""
    return shapes.FlightSearchRequest(
        OTA_AirLowFareSearchRQ=shapes.OTAAirLowFareSearchRQ(
            OriginDestinationInformation=[
                shapes.OriginDestinationInformation(
                    RPH="1",
                    DepartureDateTime="2026-08-13T08:00:00",
                    OriginLocation=shapes.AirportLocation(LocationCode="DFW"),
                    DestinationLocation=shapes.AirportLocation(LocationCode="LAX"),
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


def _booking_request() -> shapes.CreateBookingRequest:
    return shapes.CreateBookingRequest(
        travelers=[shapes.TravelerRequest(givenName="Cascade", surname="Tester")],
        contactInfo=shapes.ContactInfo(
            emails=["cascade.tester@example.com"], phones=["1-555-0100"]
        ),
        flightDetails=shapes.FlightDetails(
            flights=[
                shapes.FlightToBook(
                    flightNumber=439,
                    airlineCode="DL",
                    fromAirportCode="DFW",
                    toAirportCode="LAX",
                    departureDate="2026-08-13",
                    departureTime="07:20",
                    bookingClass="E",
                )
            ],
            flightPricing=[shapes.FlightPricing()],
        ),
    )


def test_auth_token_mints_via_real_client(client):
    """The credential smoke check: a reset credential fails here, in seconds,
    before any other test burns time. Uses the client's own token path."""
    token = asyncio.run(client._get_token())
    assert token, "empty access_token from /v2/auth/token"
    assert token.startswith("T1RL"), "unexpected token format (ATK-prefix family)"


def test_shapes_pos_field_is_dead():
    """DOCUMENTED BUG (Phase 24 work item, found by this suite 2026-07-13):
    in shapes.OTAAirLowFareSearchRQ the field name `POS` shadows the POS
    model class in the class body, so pydantic resolves the annotation to
    NoneType — the field cannot carry a value. CERT *requires* POS (400
    NotProcessed without it), so the unmodified client cannot express a
    processable BFM request. Hermetic tests never caught it because the
    mock path never sends POS.

    If this test FAILS, the shadowing was fixed — update sabre-cert-notes.md
    and drop the raw-dict workaround below."""
    assert shapes.OTAAirLowFareSearchRQ.model_fields["POS"].annotation is type(None)
    with pytest.raises(ValidationError):
        shapes.OTAAirLowFareSearchRQ(
            POS=shapes.POS(
                Source=[
                    shapes.PosSource(
                        PseudoCityCode="XXXX",
                        RequestorID=shapes.RequestorID(
                            Type="1", ID="1",
                            CompanyName=shapes.CompanyName(Code="TN"),
                        ),
                    )
                ]
            ),
            OriginDestinationInformation=[],
            TravelerInfoSummary=shapes.TravelerInfoSummary(AirTravelerAvail=[]),
        )


def test_flight_search_via_client_lacks_pos_and_gets_400(client):
    """DOCUMENTED GAP (Phase 24 work item): the best request the unmodified
    client can send (no POS — dead field) is rejected by CERT with 400
    NotProcessed, surfaced as httpx.HTTPStatusError — which is exactly what
    triggers the dispatcher's per-call mock fallback in SABRE_MODE=real."""
    import httpx

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        asyncio.run(client.flight_search(_search_request_without_pos()))
    assert excinfo.value.response.status_code == 400


def test_bfm_empty_response_omits_sections_shapes_require(client):
    """DOCUMENTED GAPS (Phase 24 work items), certified with the raw-dict
    POS workaround: (a) BFM v5 processes the request but this PCC has no
    air content — HTTP 200, itineraryCount 0, 'No Availability'; (b) empty
    responses omit scheduleDescs/legDescs/itineraryGroups, which
    shapes.FlightSearchResponse requires, so even a processable search
    breaks shape validation on empty results.

    If itineraryCount comes back > 0, the PCC gained BFM inventory —
    update sabre-cert-notes.md and re-plan Phase 24."""
    import httpx

    payload = _search_request_without_pos().model_dump(exclude_none=True)
    payload["OTA_AirLowFareSearchRQ"]["POS"] = _pos_dict()

    async def raw_search():
        token = await client._get_token()
        async with httpx.AsyncClient(base_url=CERT_BASE_URL) as http:
            return await http.post(
                "/v5/offers/shop",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=90,
            )

    resp = asyncio.run(raw_search())
    assert resp.status_code == 200
    gir = resp.json()["groupedItineraryResponse"]
    assert gir["statistics"]["itineraryCount"] == 0, (
        "PCC gained BFM inventory — update sabre-cert-notes.md / Phase 24"
    )
    with pytest.raises(ValidationError) as excinfo:
        shapes.FlightSearchResponse.model_validate(resp.json())
    missing = str(excinfo.value)
    assert "scheduleDescs" in missing and "itineraryGroups" in missing


def test_create_booking_unauthorized_tripwire(client):
    """DOCUMENTED GAP (entitlement): createBooking answers HTTP 200 with an
    UNAUTHORIZED_ACCESS errors[] payload (PassengerDetailsRQ) and no
    confirmationId, so the unmodified client raises ValidationError. No PNR
    is created server-side.

    If a booking ever SUCCEEDS here, entitlement was granted: the finally
    block cancels the PNR, and the test fails loudly so the notes and
    Phase 24 plan get updated."""
    created = None
    try:
        try:
            created = asyncio.run(client.create_booking(_booking_request()))
        except ValidationError:
            return  # the documented entitlement wall — expected path
        pytest.fail(
            f"createBooking now succeeds (PNR {created.confirmationId}) — "
            "entitlement granted; update sabre-cert-notes.md and Phase 24"
        )
    finally:
        if created is not None:
            asyncio.run(
                client.cancel_booking(
                    shapes.CancelBookingRequest(
                        confirmationId=created.confirmationId, cancelAll=True
                    )
                )
            )


def test_cancel_booking_is_authorized(client):
    """Cancel-side certification: unlike create, cancelBooking is entitled —
    a dummy PNR gets a clean RESOURCE_NOT_FOUND business error (HTTP 200),
    not an auth failure. The unmodified client raises ValidationError
    (errors-payload has no booking), NOT an HTTPStatusError — proving the
    request was authorized and processed."""
    import httpx

    with pytest.raises(ValidationError):
        asyncio.run(
            client.cancel_booking(
                shapes.CancelBookingRequest(confirmationId="ABCDEF", cancelAll=True)
            )
        )
    # explicit non-auth proof: raw call answers 200, not 401/403
    async def raw_cancel():
        token = await client._get_token()
        async with httpx.AsyncClient(base_url=CERT_BASE_URL) as http:
            return await http.post(
                "/v1/trip/orders/cancelBooking",
                headers={"Authorization": f"Bearer {token}"},
                json={"confirmationId": "ABCDEF", "cancelAll": True},
            )

    resp = asyncio.run(raw_cancel())
    assert resp.status_code == 200
    errors = resp.json().get("errors", [])
    assert any(e.get("category") == "RESOURCE_NOT_FOUND" for e in errors)
