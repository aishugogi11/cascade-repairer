"""Probe: Bargain Finder Max v5 against CERT, validated against shapes.py.

Findings (2026-07-13, recorded in ../sabre-cert-notes.md):
- POS block is REQUIRED (400 NotProcessed without it).
- TPA_Extensions/IntelliSellTransaction/RequestType "50ITINS" triggers
  'PROCESSING ERROR DETECTED' with these credentials — omit it.
- Every route/date tried returns HTTP 200 with itineraryCount 0
  ('No Availability') — the hackathon PCC appears to carry no BFM air
  content. Shopping works via GET /v1/shop/flights instead (see sweep.py).
- Empty responses OMIT scheduleDescs/legDescs/itineraryGroups, which
  shapes.py requires -> the real client raises ValidationError on empty
  searches (Phase 24 work item).

Runs inside the backend container (cwd /app) so `api.sabre.shapes` imports —
pydantic validation errors ARE the shape-delta report. Prints a trimmed,
scrubbed summary only; never the token or credentials.

Run:
    set -a && . ./config/.env && set +a && \
    docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET backend \
        python3 - < specs/2026-07-13-sabre-cert-exploration/probes/bfm_search.py
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


def post(token: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{CERT}{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {"raw": "<unparseable>"}
        return e.code, body


def build_request(depart: str) -> dict:
    pcc = os.environ["SABRE_API_USER_ID"].split(":")[2]
    return {
        "OTA_AirLowFareSearchRQ": {
            "Version": "5",
            "POS": {"Source": [{
                "PseudoCityCode": pcc,
                "RequestorID": {"Type": "1", "ID": "1",
                                "CompanyName": {"Code": "TN"}},
            }]},
            "OriginDestinationInformation": [{
                "RPH": "1",
                "DepartureDateTime": f"{depart}T08:00:00",
                "OriginLocation": {"LocationCode": "MSP"},
                "DestinationLocation": {"LocationCode": "SFO"},
            }],
            "TravelerInfoSummary": {"AirTravelerAvail": [{
                "PassengerTypeQuantity": [{"Code": "ADT", "Quantity": 1}],
            }]},
            # NB: no TravelPreferences/TPA_Extensions — 50ITINS RequestType
            # triggers 'PROCESSING ERROR DETECTED' on these credentials.
        }
    }


def main() -> int:
    depart = (date.today() + timedelta(days=14)).isoformat()
    token = mint_token()
    print(f"searching MSP->SFO {depart} (1 ADT, no TPA extensions)")
    status, body = post(token, "/v5/offers/shop", build_request(depart))
    print(f"HTTP {status}")
    if status != 200:
        print(json.dumps(body, indent=2)[:1500])
        return 1

    gir = body.get("groupedItineraryResponse", {})
    stats = gir.get("statistics", {})
    print(f"itineraryCount: {stats.get('itineraryCount')}")
    print(f"top-level keys: {sorted(gir.keys())}")

    scheds = gir.get("scheduleDescs", [])
    if scheds:
        s = scheds[0]
        print("first schedule:",
              s.get("carrier", {}).get("marketing"),
              s.get("carrier", {}).get("marketingFlightNumber"),
              s.get("departure", {}).get("airport"),
              s.get("departure", {}).get("time"),
              "->",
              s.get("arrival", {}).get("airport"),
              s.get("arrival", {}).get("time"))
    groups = gir.get("itineraryGroups", [])
    if groups and groups[0].get("itineraries"):
        fare = groups[0]["itineraries"][0]["pricingInformation"][0]["fare"]
        print("first fare:", fare["totalFare"]["totalPrice"],
              fare["totalFare"]["currency"],
              "validating carrier:", fare.get("validatingCarrierCode"))

    from api.sabre import shapes
    try:
        shapes.FlightSearchResponse.model_validate(body)
        print("shapes.FlightSearchResponse: VALIDATES")
    except Exception as e:
        print("shapes.FlightSearchResponse: DELTAS ->")
        print(str(e)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
