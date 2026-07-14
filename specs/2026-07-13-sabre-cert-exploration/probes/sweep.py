"""Probe: entitlement sweep across the Try-it-Out REST set, CERT.

Read-only endpoints only (booking create/cancel live in booking_lifecycle.py).
Prints one classified line per endpoint: WORKS / SHAPE-400 (entitled, request
schema wrong) / NOT-ENTITLED (401/403) / SERVER-ERR. Expected classifications
from the 2026-07-13 run are in the EXPECT column of ../sabre-cert-notes.md —
re-run after a credential reset to detect entitlement drift.

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


def classify(token: str, label: str, method: str, path: str, payload=None):
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
    except urllib.error.HTTPError as e:
        body = e.read()[:150].decode(errors="replace")
        if e.code in (401, 403):
            kind = "NOT-ENTITLED"
        elif e.code == 400:
            kind = "SHAPE-400   "
        else:
            kind = "SERVER-ERR  "
        print(f"{kind} [{e.code}] {label}: {body}")
    except Exception as e:
        print(f"NETWORK-ERR  {label}: {e}")


def main() -> int:
    token = mint_token()
    d30 = (date.today() + timedelta(days=30)).isoformat()
    d32 = (date.today() + timedelta(days=32)).isoformat()

    # air shopping
    classify(token, "InstaFlights GET /v1/shop/flights", "GET",
             f"/v1/shop/flights?origin=DFW&destination=LAX&departuredate={d30}"
             "&onlineitinerariesonly=N&limit=5&sortby=totalfare&order=asc")
    classify(token, "Lead Price Calendar GET /v2/shop/flights/fares", "GET",
             f"/v2/shop/flights/fares?origin=DFW&destination=LAX"
             f"&departuredate={d30}&lengthofstay=5")
    classify(token, "Destination Finder GET /v2/shop/flights/fares", "GET",
             "/v2/shop/flights/fares?origin=DFW&lengthofstay=5&topdestinations=5")
    # utility / content
    classify(token, "City pairs GET /v1/lists/supported/shop/flights/origins-destinations",
             "GET", "/v1/lists/supported/shop/flights/origins-destinations?destinationcountry=US")
    classify(token, "Supported cities GET /v1/lists/supported/cities", "GET",
             "/v1/lists/supported/cities")
    classify(token, "Airline lookup GET /v1/lists/utilities/airlines", "GET",
             "/v1/lists/utilities/airlines?airlinecode=AA")
    classify(token, "Aircraft lookup GET /v1/lists/utilities/aircraft/equipment", "GET",
             "/v1/lists/utilities/aircraft/equipment?aircraftcode=320")
    classify(token, "GeoSearch POST /v1/lists/utilities/geosearch/locations", "POST",
             "/v1/lists/utilities/geosearch/locations",
             {"GeoSearchRQ": {"GeoRef": {"Radius": 10, "UOM": "MI",
                 "RefPoint": {"Value": "SFO", "ValueContext": "CODE",
                              "RefPointType": "6"}}}})
    # hotel
    classify(token, "GetHotelAvail POST /v5/get/hotelavail", "POST",
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
    classify(token, "getBooking POST /v1/trip/orders/getBooking (dummy PNR)", "POST",
             "/v1/trip/orders/getBooking", {"confirmationId": "ABCDEF"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
