"""Probe: entitlement sweep across the Try-it-Out REST set, CERT.

Read-only endpoints only (booking create/cancel live in booking_lifecycle.py;
the one exception is modifyBooking with a dummy PNR — a clean business error,
nothing written). Prints one classified line per endpoint: WORKS / SHAPE-400
(entitled, request schema wrong) / NOT-ENTITLED (401/403) / NOT-FOUND (404) /
SERVER-ERR. Expected classifications are in ../sabre-cert-notes.md —
re-run after a credential reset to detect entitlement drift.

Exit code (hardened Phase 26): nonzero when any endpoint hit NETWORK-ERR,
so a partially failed sweep can't look successful to shell automation.

Run:
    set -a && . ./config/.env && set +a && \
    docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET backend \
        python3 - < specs/2026-07-13-sabre-cert-exploration/probes/sweep.py
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

CERT = "https://api.cert.platform.sabre.com"


def mint_token() -> str:
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    user_id, password = os.environ["SABRE_API_USER_ID"], os.environ["SABRE_API_SECRET"]
    secret = b64(f"{b64(user_id)}:{b64(password)}")
    req = urllib.request.Request(
        f"{CERT}/v2/auth/token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={"Authorization": f"Basic {secret}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


def classify(token: str, label: str, method: str, path: str, payload=None) -> str:
    """One classified line per endpoint; returns the outcome kind so main()
    can exit nonzero when a NETWORK-ERR made the sweep incomplete."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{CERT}{path}", data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read()[:150].decode(errors="replace")
            print(f"WORKS        [{resp.status}] {label}: {body}")
            return "WORKS"
    except urllib.error.HTTPError as e:
        body = e.read()[:150].decode(errors="replace")
        if e.code in (401, 403):
            kind = "NOT-ENTITLED"
        elif e.code == 400:
            kind = "SHAPE-400   "
        elif e.code == 404:
            kind = "NOT-FOUND   "
        else:
            kind = "SERVER-ERR  "
        print(f"{kind} [{e.code}] {label}: {body}")
        return kind.strip()
    except Exception as e:
        print(f"NETWORK-ERR  {label}: {e}")
        return "NETWORK-ERR"


def main() -> int:
    token = mint_token()
    d30 = (date.today() + timedelta(days=30)).isoformat()
    d32 = (date.today() + timedelta(days=32)).isoformat()

    outcomes: list = []

    def probe(label: str, method: str, path: str, payload=None) -> None:
        outcomes.append(classify(token, label, method, path, payload))

    # air shopping
    probe("InstaFlights GET /v1/shop/flights", "GET",
          f"/v1/shop/flights?origin=DFW&destination=LAX&departuredate={d30}"
          "&onlineitinerariesonly=N&limit=5&sortby=totalfare&order=asc")
    probe("Lead Price Calendar GET /v2/shop/flights/fares", "GET",
          f"/v2/shop/flights/fares?origin=DFW&destination=LAX"
          f"&departuredate={d30}&lengthofstay=5")
    probe("Destination Finder GET /v2/shop/flights/fares", "GET",
          "/v2/shop/flights/fares?origin=DFW&lengthofstay=5&topdestinations=5")
    # utility / content
    probe("City pairs GET /v1/lists/supported/shop/flights/origins-destinations",
          "GET", "/v1/lists/supported/shop/flights/origins-destinations?destinationcountry=US")
    probe("Supported cities GET /v1/lists/supported/cities", "GET",
          "/v1/lists/supported/cities")
    probe("Airline lookup GET /v1/lists/utilities/airlines", "GET",
          "/v1/lists/utilities/airlines?airlinecode=AA")
    probe("Aircraft lookup GET /v1/lists/utilities/aircraft/equipment", "GET",
          "/v1/lists/utilities/aircraft/equipment?aircraftcode=320")
    probe("GeoSearch POST /v1/lists/utilities/geosearch/locations", "POST",
          "/v1/lists/utilities/geosearch/locations",
          {"GeoSearchRQ": {"GeoRef": {"Radius": 10, "UOM": "MI",
              "RefPoint": {"Value": "SFO", "ValueContext": "CODE",
                           "RefPointType": "6"}}}})
    # hotel
    probe("GetHotelAvail POST /v5/get/hotelavail", "POST",
          "/v5/get/hotelavail",
          {"GetHotelAvailRQ": {"SearchCriteria": {
              "OffSet": 1, "SortBy": "TotalRate", "SortOrder": "ASC",
              "GeoSearch": {"GeoRef": {"Radius": 10, "UOM": "MI",
                  "RefPoint": {"Value": "SFO", "ValueContext": "CODE",
                               "RefPointType": "6"}}},
              "RateInfoRef": {"CurrencyCode": "USD",
                  "StayDateRange": {"StartDate": d30, "EndDate": d32},
                  "Rooms": {"Room": [{"Index": 1, "Adults": 1}]}}}}})
    # booking management (read side; create side is booking_lifecycle.py)
    probe("getBooking POST /v1/trip/orders/getBooking (dummy PNR)", "POST",
          "/v1/trip/orders/getBooking", {"confirmationId": "ABCDEF"})

    # --- Phase 26 domain extension (executed classifications, 2026-07-14) ---
    # air schedules: no standalone REST endpoint exists in CERT's rest table
    # (candidates /v{1,3}/shop/flights/schedules, /v{1,2}/air/schedules all
    # 404) — schedule content rides in InstaFlights segments. The probe stays
    # so a later appearance of the endpoint is detected as drift.
    probe("Air schedules GET /v1/shop/flights/schedules", "GET",
          f"/v1/shop/flights/schedules?origin=DFW&destination=LAX&departuredate={d30}")
    # air availability: not entitled. CERT's 2SG gateway flaps between 403
    # ERR.2SG.SEC.NOT_AUTHORIZED and an empty-body 404 on back-to-back calls
    # (observed 2026-07-14), so NOT-ENTITLED and NOT-FOUND are both this
    # denial — either line is the same classification.
    probe("Air availability POST /v2/air/availability", "POST",
          "/v2/air/availability", {})
    # exchange/reshop: two distinct APIs — exchange shopping (not entitled;
    # same 403/404 gateway flap as air availability) and flight reshop
    # (entitled; 400 asks for `journeys`, proving the request cleared
    # authorization into payload validation).
    probe("Exchange Shop POST /v3/exchange/shop", "POST", "/v3/exchange/shop",
          {"ExchangeShoppingRQ": {"PNRLocator": "ABCDEF"}})
    probe("Flight Reshop POST /v1/offers/flightReshop", "POST",
          "/v1/offers/flightReshop", {"confirmationId": "ABCDEF"})
    # ground/car: Car Availability (beta REST) is absent from CERT's rest
    # table (POST/GET /v2.4.0/shop/cars and successors all 404) — car/ground
    # is SOAP-only territory for these credentials.
    probe("Car Availability POST /v2.4.0/shop/cars", "POST",
          "/v2.4.0/shop/cars",
          {"GetVehAvailRQ": {"SearchCriteria": {
              "PickUpDate": d30, "PickUpTime": "10:00",
              "ReturnDate": d32, "ReturnTime": "10:00",
              "PickUpLocation": {"LocationCode": "LAX"},
              "ReturnLocation": {"LocationCode": "LAX"}}}})
    # EnhancedSeatMap via POST (replaces the notes-only GET 404 row): the
    # REST wrapper lives at v3.0.0; SHAPE-400 = entitled, schema wrong.
    probe("EnhancedSeatMap POST /v3.0.0/book/flights/seatmaps", "POST",
          "/v3.0.0/book/flights/seatmaps?mode=seatmaps",
          {"EnhancedSeatMapRQ": {"SeatMapQueryEnhanced": {"RequestType": "Payload"}}})
    # modifyBooking via dummy PNR (D2): the full documented payload clears
    # field validation and answers HTTP 200 + BOOKING_NOT_FOUND — a clean
    # business error proving authorization (the wall is create-side only).
    # Nothing is written: the PNR does not exist.
    probe("modifyBooking POST /v1/trip/orders/modifyBooking (dummy PNR)", "POST",
          "/v1/trip/orders/modifyBooking",
          {"confirmationId": "ABCDEF",
           "bookingSignature": "DUMMYSIGNATURE",
           "before": {},
           "after": {
               "hotels": [{
                   "itemId": "12",
                   "checkInDate": d30,
                   "checkOutDate": d32,
                   "leadTravelerIndex": 1,
                   "paymentPolicy": "GUARANTEE",
                   "room": {"travelerIndices": [1]},
                   "numberOfGuests": 1}],
               "travelers": [{"givenName": "Cascade", "surname": "Tester"}]},
           "retrieveBooking": True,
           "receivedFrom": "API"})

    network_errors = outcomes.count("NETWORK-ERR")
    if network_errors:
        print(f"SWEEP INCOMPLETE: {network_errors} endpoint(s) hit NETWORK-ERR",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
