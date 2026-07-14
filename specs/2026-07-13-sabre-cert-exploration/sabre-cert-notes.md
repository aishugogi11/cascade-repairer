# Sabre CERT Notes — Phase 25

Successor to `specs/2026-07-08-sabre-tools/sabre-api-notes.md` (the Phase 6 docs pull).
Where that file recorded what the *documentation* says, this one records what the CERT
environment *actually does* with our hackathon developer credentials. Exploration date:
2026-07-13. Credentials: the developer user + API key in `config/.env`
(`SABRE_API_USER_ID` / `SABRE_API_SECRET`) — values never appear in this file.

Confidence labels: **verified-live** (we ran it against CERT and saw the response),
**docs-only** (claimed by documentation, not exercised), **inferred**.

## Auth — verified-live (2026-07-13, HTTP 200)

The Phase 6 recipe works unchanged against CERT with the hackathon credentials:

- `SABRE_API_USER_ID` is the Sabre **client ID**, already in the full
  `V1:{user}:{group}:{domain}` triplet form (ours ends `:EXT`). Store it verbatim.
- `SABRE_API_SECRET` is the paired **password** (short, ~8 chars). Store it verbatim.
- Basic secret construction (the v2 recipe, corroborated by
  developer.sabre.com "REST APIs: token credentials"):

  ```
  secret = base64( base64(client_id) + ":" + base64(password) )
  ```

- Token mint: `POST https://api.cert.platform.sabre.com/v2/auth/token`,
  `Content-Type: application/x-www-form-urlencoded`, body `grant_type=client_credentials`,
  header `Authorization: Basic {secret}`.
- Observed response: `token_type: bearer`, `expires_in: 604800` (7 days), token prefix
  `T1RLAQ…`, length 376 chars — exactly the shape `shapes.TokenResponse` models.
  The v3 password grant was **not needed**; v2 works with these credentials.

Smoke check (run first, every session — Sabre periodically resets test credentials):

```
set -a && . ./config/.env && set +a && \
docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET backend \
    python3 - < specs/2026-07-13-sabre-cert-exploration/probes/auth_check.py
```

### Phase 24 env bridge (flip prep)

`backend/api/sabre/real_client.py` reads `SABRE_BASE_URL` + `SABRE_CLIENT_SECRET`
(the pre-composed Basic secret), not the raw pair. To run the unmodified client:

```bash
export SABRE_BASE_URL="https://api.cert.platform.sabre.com"
export SABRE_CLIENT_SECRET="$(python3 - <<'PY'
import base64, os
b64 = lambda s: base64.b64encode(s.encode()).decode()
print(b64(f"{b64(os.environ['SABRE_API_USER_ID'])}:{b64(os.environ['SABRE_API_SECRET'])}"))
PY
)"
```

For the Cloud Run flip these two become `--update-env-vars` entries alongside
`SABRE_MODE=real`. The raw pair stays in `config/.env` regardless — it is what gets
re-entered when Sabre resets the test credentials.

Local-dev caveats (learned 2026-07-13): the running compose container does **not** see
vars newly added to `config/.env` (env_file bakes at container creation — recreate with
`docker compose up -d backend`, or pass through `exec -e VAR`); and host `python3.14`
lacks a CA bundle, so HTTPS probes must run inside the container.

## Endpoint matrix — verified-live 2026-07-13

Re-run `probes/sweep.py` after any credential reset to detect entitlement drift.

| API | Endpoint | Result |
|---|---|---|
| **InstaFlights (Flight Search)** | `GET /v1/shop/flights` | ✅ **WORKS** — real priced itineraries (DL/UA/AA, real fares). Caveat: `onlineitinerariesonly=Y` triggers a CERT-side **500** (Java NPE in `raf`); always send `N`. |
| Lead Price Calendar | `GET /v2/shop/flights/fares?origin&destination` | ✅ WORKS (e.g. DFW→LAX lowest $344.80 DL) |
| Destination Finder | `GET /v2/shop/flights/fares?origin&topdestinations` | ✅ WORKS |
| City pairs lookup | `GET /v1/lists/supported/shop/flights/origins-destinations` | ✅ WORKS — the supported-market list for InstaFlights |
| Supported cities | `GET /v1/lists/supported/cities` | ✅ WORKS |
| Airline / aircraft lookup | `GET /v1/lists/utilities/{airlines,aircraft/equipment}` | ✅ WORKS |
| **Bargain Finder Max v5** | `POST /v5/offers/shop` | ⚠️ **Entitled but empty**: request processes only with a POS block and *without* IntelliSell `RequestType` (`50ITINS` → `PROCESSING ERROR DETECTED`); every route/date returns `itineraryCount: 0` / "No Availability" — the hackathon PCC has **no BFM air content agreement**. |
| **Booking Mgmt createBooking** | `POST /v1/trip/orders/createBooking` | ❌ **NOT ENTITLED**: HTTP 200 + `errors[]` `UNAUTHORIZED_ACCESS` ("The service PassengerDetailsRQ returned an authorization failure. Please verify the used credentials with your account manager."). No PNR is created. |
| Booking Mgmt cancelBooking | `POST /v1/trip/orders/cancelBooking` | ✅ Authorized (dummy PNR → clean `RESOURCE_NOT_FOUND`, not an auth error) — the wall is create-side only |
| Booking Mgmt getBooking | `POST /v1/trip/orders/getBooking` | ✅ Authorized (same evidence) |
| Booking Mgmt modifyBooking | `POST /v1/trip/orders/modifyBooking` | ➖ **Untestable**: needs an existing PNR, and create is entitlement-blocked upstream. **inferred** same authorization as cancel/get. |
| GetHotelAvail v5 | `POST /v5/get/hotelavail` | ⚠️ Entitled, request schema not yet cracked (`VALIDATION_FAILED`, "matched 0 out of 3" oneOf schemas) — shape work, not an entitlement problem |
| Geo Search | `POST /v1/lists/utilities/geosearch/locations` | ⚠️ Entitled, schema incomplete (`cvc-complex-type` validation error); `POST /v2/geo/search` is 404 |
| EnhancedSeatMap | `GET /v5/book/flights/seatmaps` | 404 on GET probe (POST-only API; untested further) |

Rate limits: none hit across ~40 calls in one session (several BFM + InstaFlights calls
back-to-back). No `429` or rate-limit headers observed. **inferred**: hackathon-tier
limits exist but are above exploration volume.

## Deltas vs. mock shapes (`backend/api/sabre/shapes.py`) — all Phase 24 work items

1. **`OTAAirLowFareSearchRQ.POS` is a dead field (latent bug, found 2026-07-13).**
   The field name `POS` shadows the `POS` model class inside the class body, so
   pydantic resolves the annotation to `NoneType` — the field can never carry a value
   (`Input should be None`). CERT **requires** POS (400 `NotProcessed` without it), so
   the unmodified real client cannot express a processable BFM request. Never caught
   hermetically because the mock path omits POS. Fix: rename the field's type
   reference (e.g. alias the class `POS as PosModel`) or use a string annotation.
   Certified by `tests/test_sabre_cert.py::test_shapes_pos_field_is_dead`.
2. **Empty BFM responses omit `scheduleDescs`/`legDescs`/`itineraryGroups`** — the
   response model requires them, so 0-result searches raise `ValidationError` in the
   real client (dispatcher then falls back to mock — graceful in the demo, but real
   mode can never report "no flights found"). Fix: make the three lists optional/default-empty.
3. **Booking Management failures are HTTP 200 + `errors[]`** (+ request echo), with no
   `confirmationId`/`booking` — `raise_for_status()` passes and `model_validate` raises.
   The mock fallback masks this, but Phase 24 should detect `errors[]` explicitly and
   surface a speakable failure instead of a silent mock swap.
4. BFM `TravelPreferences`/`TPA_Extensions` are modeled but **must not be sent** with
   these credentials (see matrix); `exclude_none=True` already omits them when unset —
   just never set them in real mode.
5. InstaFlights (`/v1/shop/flights`) is **not modeled at all** in shapes.py — response
   root `PricedItineraries[].AirItinerary.OriginDestinationOptions.OriginDestinationOption[]
   .FlightSegment[]` with `DepartureDateTime` (no UTC offset), `MarketingAirline.Code`,
   `ResBookDesigCode`, and `AirItineraryPricingInfo.ItinTotalFare`. New shapes needed if
   promoted (see recommendations).

Timezone note for the Phase 24 conversion residual: InstaFlights `DepartureDateTime`
carries **no offset** (`2026-08-13T07:20:00` = airport-local), while BFM
`departure.time` carries offsets (`08:00:00-05:00`, per docs pull). Conversion
handling must branch by source API.

## Flight Search API v1 (deal-engine gate) — ANSWERED: YES ✅

`GET /v1/shop/flights` is entitled and returns real multi-airline priced itineraries
on CERT (verified-live). The backlogged deal-manufacturing engine's gating question is
answered **go** from an API-entitlement standpoint. Supported markets are enumerable via
`GET /v1/lists/supported/shop/flights/origins-destinations`. Caveats: send
`onlineitinerariesonly=N` (Y → CERT 500), and fares/inventory are CERT test data.

## What this unlocks for the demo

**The headline:** with the hackathon credentials, **Sabre = real shopping, mock booking.**
Everything read-only works today; everything that writes a PNR is entitlement-blocked.

Recommendations for the next replan, in priority order:

1. **Promote real Sabre *search* into the demo path (new small phase, before Phase 24):**
   swap `search_flights_impl`'s data source to `GET /v1/shop/flights` (InstaFlights) in
   real mode — real airlines, real fares, real routes spoken by the agent, supported-city
   validation for free. This is demoable Sabre-realness without any booking entitlement.
   BFM v5 stays parked unless Sabre grants air content (ask at the event — see #3).
2. **Keep booking in `SABRE_MODE=mock` and stop treating the full flip as pending:**
   re-scope Phase 24's flip to "flip search real, keep booking mock" — `createBooking`
   is a hard entitlement wall (`PassengerDetailsRQ` unauthorized), not a debugging task.
   The per-call fallback already makes this seamless, but add explicit `errors[]`
   detection (delta #3) so a mid-demo entitlement surprise can't silently mock-swap.
3. **Event-day ask for Sabre staff (put it on the day-plan):** can hackathon teams get
   a PCC with BFM air content + `PassengerDetailsRQ` (create) authorization? Both walls
   name the account manager as the unlock. If yes on-site, deltas #1–#3 are the entire
   real-booking punch list.
4. **Deal engine: entitlement-go** (see gate answer). If promoted post-Phase 23, it
   rides on InstaFlights + Lead Price Calendar (`extend_stay` scans lengthofstay fare
   curves naturally).
5. **Hotel leg stays mock for now**: GetHotelAvail v5 is entitled but needs schema
   work; only worth the time if the Cascade hotel-repair beat should speak real hotel
   names/rates.
6. **Credential hygiene:** test creds reset periodically — run `probes/auth_check.py`
   (or `pytest -m cert`) the morning of the event; re-run `probes/sweep.py` to catch
   entitlement drift. Free hub access lasts 7 days from signup (kickoff PDF) — verify
   the developer user still authenticates mid-week.
