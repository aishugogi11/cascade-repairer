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
from datetime import date, timedelta

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


def _future_travel_date(days_ahead: int = 30) -> str:
    """Computed travel date (the probes' pattern) so the suite stays valid on
    any run date — never hard-code a calendar day."""
    return (date.today() + timedelta(days=days_ahead)).isoformat()


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
                    DepartureDateTime=f"{_future_travel_date()}T08:00:00",
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
                    departureDate=_future_travel_date(),
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


def _raw_response_from_validation_error(exc: ValidationError) -> dict | None:
    """Recover the raw payload `model_validate` received. Each error's
    `input` is the value at its `loc`, so the shallowest loc walks back
    closest to the root — a root-level missing-field error (how the
    entitlement wall and any drifted success both fail validation) carries
    the whole response dict."""
    best: dict | None = None
    best_depth: int | None = None
    for err in exc.errors():
        candidate = err.get("input")
        if isinstance(candidate, dict):
            depth = len(err.get("loc", ()))
            if best_depth is None or depth < best_depth:
                best, best_depth = candidate, depth
    return best


def _attempt_create_harvesting_confirmation(client, request):
    """Attempt create_booking, harvesting any confirmationId no matter how
    the response arrives — a validated model, or a raw payload recovered
    from the ValidationError the unmodified client raises on undocumented
    shapes. Returns (created_model_or_None, raw_dict_or_None,
    confirmation_or_None). The client is injected so the hermetic suite
    (test_sabre_cert_cleanup.py) can drive this exact flow with a fake."""
    try:
        created = asyncio.run(client.create_booking(request))
    except ValidationError as exc:
        raw = _raw_response_from_validation_error(exc)
        harvested = raw.get("confirmationId") if raw else None
        return None, raw, harvested or None
    return created, None, created.confirmationId


def _cancel_harvested_pnr(client, confirmation_id: str) -> None:
    asyncio.run(
        client.cancel_booking(
            shapes.CancelBookingRequest(
                confirmationId=confirmation_id, cancelAll=True
            )
        )
    )


def _run_create_booking_tripwire(client, request) -> None:
    """The tripwire flow: the ONLY acceptable outcome is the documented
    entitlement wall — a raw errors[] payload whose categories include
    UNAUTHORIZED_ACCESS. A validated success, an unrecoverable payload, or
    any other category set is drift and fails loudly. Whatever the outcome,
    the finally block cancels any harvested confirmationId, so a
    created-but-shape-drifted PNR can never leak."""
    harvested = None
    try:
        created, raw, harvested = _attempt_create_harvesting_confirmation(
            client, request
        )
        if created is not None:
            pytest.fail(
                f"createBooking now succeeds (PNR {created.confirmationId}) — "
                "entitlement granted; update sabre-cert-notes.md and Phase 24"
            )
        if raw is None:
            pytest.fail(
                "create_booking raised ValidationError but the raw response "
                "payload could not be recovered — response drift; probe live "
                "with probes/booking_lifecycle.py"
            )
        # The wall's marker: UNAUTHORIZED_ACCESS. CERT carries it in `type`
        # (`category` is UNAUTHORIZED — verified live 2026-07-14), so check
        # both fields rather than trusting the docs' field placement.
        tokens = {
            token
            for err in raw.get("errors", [])
            if isinstance(err, dict)
            for token in (err.get("category"), err.get("type"))
        }
        if "UNAUTHORIZED_ACCESS" not in tokens:
            pytest.fail(
                "createBooking no longer answers the documented entitlement "
                f"wall: errors[] category/type values {sorted(t for t in tokens if t)} "
                "lack UNAUTHORIZED_ACCESS — update sabre-cert-notes.md and "
                "Phase 24"
                + (f" (harvested PNR {harvested} cancelled in cleanup)" if harvested else "")
            )
    finally:
        if harvested:
            _cancel_harvested_pnr(client, harvested)


def test_create_booking_unauthorized_tripwire(client):
    """DOCUMENTED GAP (entitlement): createBooking answers HTTP 200 with an
    UNAUTHORIZED_ACCESS errors[] payload (PassengerDetailsRQ) and no
    confirmationId, so the unmodified client raises ValidationError. No PNR
    is created server-side.

    Reworked for Phase 26: a ValidationError alone is no longer proof of the
    wall — the raw payload must carry the UNAUTHORIZED_ACCESS category, and
    any confirmationId that arrives (validated OR inside a drifted payload)
    is cancelled in a finally block before the test resolves."""
    _run_create_booking_tripwire(client, _booking_request())


def test_instaflights_supported_markets_live(client):
    """Phase 27: the supported-markets list the concierge's best-effort
    market check rides on — the live shape validates and carries the
    verified-live DFW→LAX pair. If this fails, the market check silently
    degrades to no-validation (by design), but the drift should be known."""
    markets = asyncio.run(client.supported_markets())
    pairs = {
        (p.OriginLocation.AirportCode, p.DestinationLocation.AirportCode)
        for p in markets.OriginDestinationLocations
    }
    assert pairs, "supported-markets list came back empty"
    assert ("DFW", "LAX") in pairs, (
        "DFW→LAX left the supported-markets list — update sabre-cert-notes.md"
    )


def test_instaflights_search_returns_real_priced_itineraries(client):
    """Phase 27: the demo path's search — ≥1 real priced itinerary for a
    supported pair on a computed future date, and the concierge parser
    yields speakable PT-converted options from it (every parsed option
    carries a mappable airport pair by construction — unmappable ones are
    skipped, and all-skipped would fail the non-empty assertion)."""
    from api.concierge import _parse_instaflights_options

    response = asyncio.run(
        client.instaflights_search(
            shapes.InstaFlightsRequest(
                origin="DFW",
                destination="LAX",
                departuredate=_future_travel_date(),
                limit=10,
            )
        )
    )
    assert response.PricedItineraries, (
        "InstaFlights returned no priced itineraries for DFW→LAX — "
        "entitlement or content drift; update sabre-cert-notes.md"
    )

    options = _parse_instaflights_options(response, "DFW", "LAX")
    assert options, "no itinerary had a mappable airport pair"
    for option in options:
        assert option.depart_date and option.arrive_date  # PT-converted dates
        assert len(option.depart_time) == 5 and ":" in option.depart_time
        assert option.price > 0
        assert option.airline  # real carrier code in the structured field
        assert option.airline not in option.spoken  # never spoken


def test_supported_markets_airports_all_resolve_a_timezone(client):
    """Phase 28 timezone-table parity: every airport code on either side of
    the LIVE supported-markets list resolves via airport_zone — so a
    supported route can never be silently unmappable (the parser skips
    itineraries touching unmapped airports, which on a fully unmapped pair
    degrades a real route to the no-flights line). If this fails, add the
    named codes to AIRPORT_TZ (grouped-by-zone style) in the same commit."""
    from api.sabre.airport_tz import airport_zone

    markets = asyncio.run(client.supported_markets())
    codes = set()
    for pair in markets.OriginDestinationLocations:
        codes.add(pair.OriginLocation.AirportCode.strip().upper())
        codes.add(pair.DestinationLocation.AirportCode.strip().upper())
    assert codes, "supported-markets list came back empty"

    unmapped = sorted(code for code in codes if airport_zone(code) is None)
    assert not unmapped, (
        f"{len(unmapped)} supported-market airport codes missing from "
        f"AIRPORT_TZ: {unmapped}"
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
