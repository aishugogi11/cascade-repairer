"""Probe: Booking Management create -> cancel against CERT, cancel in finally.

Findings (2026-07-13, recorded in ../sabre-cert-notes.md):
- createBooking returns HTTP 200 with an `errors` array:
  UNAUTHORIZED_ACCESS — "The service PassengerDetailsRQ returned an
  authorization failure." The hackathon credentials CANNOT create PNRs.
  No confirmationId is returned, so nothing is written server-side.
- cancelBooking / getBooking ARE authorized (dummy PNR returns a clean
  RESOURCE_NOT_FOUND, not an auth error) — the wall is create-side only.
- BM failure responses are 200 + {timestamp, errors[], request-echo} with
  no confirmationId/booking -> shapes.CreateBookingResponse raises
  ValidationError on them (how the dispatcher's mock fallback triggers).

The flight candidate is sourced live from GET /v1/shop/flights (InstaFlights)
because BFM v5 returns no inventory on this PCC. If createBooking ever
succeeds (entitlement granted later), the finally block cancels the PNR.

Exit code (hardened Phase 26): nonzero when createBooking drifts from the
documented UNAUTHORIZED_ACCESS wall — no UNAUTHORIZED_ACCESS among the
errors[] category/type values (CERT carries it in `type`; `category` is
UNAUTHORIZED), an empty errors[] without a confirmationId, or an
unexpected success.

Run:
    set -a && . ./config/.env && set +a && \
    docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET backend \
        python3 - < specs/2026-07-13-sabre-cert-exploration/probes/booking_lifecycle.py
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


def call(token: str, method: str, path: str, payload=None, timeout=180):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{CERT}{path}", data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def main() -> int:
    token = mint_token()
    depart = (date.today() + timedelta(days=30)).isoformat()
    # onlineitinerariesonly=Y 500s on CERT (server-side NPE); use N.
    st, shop = call(token, "GET",
                    f"/v1/shop/flights?origin=DFW&destination=LAX"
                    f"&departuredate={depart}&onlineitinerariesonly=N"
                    f"&limit=3&sortby=totalfare&order=asc", timeout=90)
    if st != 200 or not shop.get("PricedItineraries"):
        print(f"FAIL: InstaFlights returned HTTP {st} / no itineraries")
        return 1
    seg = (shop["PricedItineraries"][0]["AirItinerary"]
           ["OriginDestinationOptions"]["OriginDestinationOption"][0]
           ["FlightSegment"][0])
    dep_dt = seg["DepartureDateTime"]
    flight = {
        "flightNumber": int(seg["FlightNumber"]),
        "airlineCode": seg["MarketingAirline"]["Code"],
        "fromAirportCode": seg["DepartureAirport"]["LocationCode"],
        "toAirportCode": seg["ArrivalAirport"]["LocationCode"],
        "departureDate": dep_dt[:10],
        "departureTime": dep_dt[11:16],
        "bookingClass": seg.get("ResBookDesigCode", "Y"),
        "flightStatusCode": "NN",
    }
    print("booking candidate:", flight)

    create_rq = {
        "travelers": [{"givenName": "Cascade", "surname": "Tester",
                       "passengerCode": "ADT"}],
        "contactInfo": {"emails": ["cascade.tester@example.com"],
                        "phones": ["1-555-0100"]},
        "flightDetails": {"flights": [flight], "flightPricing": [{}]},
    }
    conf_id = None
    drift = False
    try:
        st, created = call(token, "POST", "/v1/trip/orders/createBooking", create_rq)
        print(f"createBooking: HTTP {st}")
        conf_id = created.get("confirmationId")
        if conf_id:
            print("  UNEXPECTED SUCCESS — PNR", conf_id,
                  "(entitlement granted? update sabre-cert-notes.md)")
            drift = True  # the documented create-side wall is gone
        else:
            errors = created.get("errors", [])
            for err in errors:
                print("  error:", err.get("category"), err.get("type"),
                      "-", (err.get("description") or "")[:120])
            # CERT carries the marker in `type` (`category` is UNAUTHORIZED,
            # verified live 2026-07-14) — check both fields.
            tokens = {err.get("category") for err in errors} | \
                     {err.get("type") for err in errors}
            if "UNAUTHORIZED_ACCESS" not in tokens:
                print("  DRIFT: expected the documented UNAUTHORIZED_ACCESS "
                      "entitlement wall; errors[] category/type values were",
                      sorted(t for t in tokens if t) or "empty")
                drift = True
    finally:
        if conf_id:
            st2, cancelled = call(token, "POST", "/v1/trip/orders/cancelBooking",
                                  {"confirmationId": conf_id,
                                   "retrieveBooking": True, "cancelAll": True,
                                   "errorHandlingPolicy": "HALT_ON_ERROR"})
            print(f"cancelBooking: HTTP {st2}",
                  "(cleanup of unexpected PNR)" if st2 == 200 else "!! CHECK PNR MANUALLY")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
