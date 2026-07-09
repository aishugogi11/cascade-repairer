# Validation — Sabre Tools (Phase 6)

## Automated

From `backend/`:

```
python -m pytest
```

- [ ] The whole suite exits 0, hermetically: no GCP credentials, no
      `OPENAI_API_KEY`, no network. GCP is mocked at the `bq_helper`
      boundary; Sabre real-mode failure is simulated, never dialed.

Specific assertions that must exist and pass:

- [ ] **Shape fidelity** — mock client responses validate against the
      `shapes.py` pydantic models built from `sabre-api-notes.md`, for every
      documented operation (flight search, book, cancel, rebook; hotel book,
      date change).
- [ ] **Flag dispatch** — with `SABRE_MODE=mock` (and unset) the dispatcher
      calls the mock; with `SABRE_MODE=real` it calls the real client. The
      flag is read per call (`monkeypatch.setenv` mid-test changes behavior).
- [ ] **Auto-fallback** — in `real` mode, a raising real client yields the
      mock result for that call and a `logger.warning` naming the operation
      (asserted via `caplog`).
- [ ] **Failed writes surface (Phase 5 gap 1)** — `_repair_one` produces a
      `status="error"` completion event when `update_status` returns
      `success=False`, and when it returns `affected_rows == 0`; the happy
      path still reports `ok`.
- [ ] **Tool writes** — each of the six repair tools, with `bq_helper`
      mocked, issues the expected `bookings` insert/update and
      `itinerary_items` status DML, and returns a readable payload
      (confirmation ref, new times).
- [ ] **Injector** — `POST /v1/disruption/break_flight` flips the trip's
      flight item to `broken`; returns 404 for a trip without a flight item;
      reports an error (not success) on a failed or 0-row write.

## Manual walkthrough

Against real BigQuery — locally with credentials or on the deployed Cloud Run
service. This is the Phase 5 gap-2 proof; record the actual query output as
evidence (validation report or PR description).

- [ ] Seed a booked demo trip with all five item types; confirm five
      `itinerary_items` rows with status `booked`.
- [ ] Note the current time, then call the disruption injector; the flight
      row reads `broken` with a fresh `updated_at`.
- [ ] Run the repair endpoint; while repairs run, rows pass through
      `repairing`; when complete, **all five rows read `fixed` with
      `updated_at` stamps later than the disruption time** — real rows, not
      demo-id DML emission.
- [ ] Flip `SABRE_MODE=real` (no sandbox creds configured) and repeat one
      repair: the call succeeds via auto-fallback and the fallback warning
      appears in the logs — event-day insurance demonstrated.
- [ ] Edge: call the injector twice (idempotent — second call is a clean
      no-op or re-flip, not a 500); call the injector with an unknown
      `trip_id` (404, no write).

## Tone check

- [ ] `sabre-api-notes.md`, tool docstrings/descriptions, and endpoint
      responses read as plain engineering prose: what the operation does,
      takes, and returns — numbers and refs included, no marketing.

## Definition of done

- All automated assertions pass in CI (pytest inside the built image; a
  failure blocks the deploy).
- The manual walkthrough is complete with captured BigQuery output proving
  real rows flip `repairing → fixed` with fresh `updated_at`.
- `sabre-api-notes.md` exists and the mock layer's shapes trace to it.
- Both Phase 5 carry-over gaps are demonstrably closed.
- Phase 6 marked `[x] COMPLETE` in `specs/roadmap.md`.

## Josh validation 
1. Get the service URL
URL=$(gcloud run services describe vocal-bridge-be-dev --region us-west1 --format 'value(status.url)')
```https://vocal-bridge-be-dev-24105435206.us-west1.run.app/docs#/sabre_tools/seed_trip_v1_sabre_tools_seed_trip_post```

2. Seed a demo trip and confirm five booked rows
curl -s -X POST $URL/v1/sabre_tools/seed_trip -H 'Content-Type: application/json' -d '{}'
# note the trip_id from the response, then:
bq query --use_legacy_sql=false "SELECT item_id, type, status, updated_at FROM vocal_bridge.itinerary_items WHERE trip_id='<TRIP_ID>' ORDER BY type"

```
curl -X 'POST' \
  'https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/sabre_tools/seed_trip' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "user_id": "demo-traveler",
  "title": "The Complete Trip — hackathon demo"
}'

{
  "trip_id": "154cec56-8ee5-4c67-922e-d66918882f99",
  "items": [
    {
      "item_id": "cc32b64d-d204-4564-b8df-f7855476e718",
      "type": "flight",
      "status": "booked"
    },
    {
      "item_id": "832508dc-290a-41a2-8267-c9e92db8a538",
      "type": "hotel",
      "status": "booked"
    },
    {
      "item_id": "7c31c71a-86d6-4ad2-8aad-960cf84fbaa9",
      "type": "ground",
      "status": "booked"
    },
    {
      "item_id": "8fde29bb-15bd-40a9-bc94-e92d6f5d23ad",
      "type": "dining",
      "status": "booked"
    },
    {
      "item_id": "b782faa2-3f8b-4f9c-b3e2-ee39292e63a8",
      "type": "experience",
      "status": "booked"
    }
  ],
  "bookings": [
    {
      "booking_id": "db82403a-74ba-4d85-babf-1fe8de7cd95b",
      "item_id": "cc32b64d-d204-4564-b8df-f7855476e718"
    },
    {
      "booking_id": "a9a30425-ff7f-4e93-b040-8ef54fbcd4b4",
      "item_id": "832508dc-290a-41a2-8267-c9e92db8a538"
    }
  ]
}

SELECT * FROM `vocal-bridge-hackathon.vocal_bridge.itinerary_items` LIMIT 1000
item_id	trip_id	type	status	provider	provider_ref	start_ts	end_ts	location	details	price	currency	updated_at
b782faa2-3f8b-4f9c-b3e2-ee39292e63a8	154cec56-8ee5-4c67-922e-d66918882f99	experience	booked	other	SEED-EXPERIENCE-4A42CD	2026-07-19 10:00:00.000000 UTC	2026-07-19 12:00:00.000000 UTC	Computer History Museum		37.5	USD	2026-07-08 18:08:13.969548 UTC
8fde29bb-15bd-40a9-bc94-e92d6f5d23ad	154cec56-8ee5-4c67-922e-d66918882f99	dining	booked	other	SEED-DINING-9E4288	2026-07-17 19:00:00.000000 UTC	2026-07-17 21:00:00.000000 UTC	"Castro St, Mountain View"		120.0	USD	2026-07-08 18:08:12.779509 UTC
7c31c71a-86d6-4ad2-8aad-960cf84fbaa9	154cec56-8ee5-4c67-922e-d66918882f99	ground	booked	other	SEED-GROUND-6667E2	2026-07-17 12:30:00.000000 UTC	2026-07-17 13:15:00.000000 UTC	SFO -> Mountain View		58.0	USD	2026-07-08 18:08:11.444897 UTC
832508dc-290a-41a2-8267-c9e92db8a538	154cec56-8ee5-4c67-922e-d66918882f99	hotel	booked	sabre	SEED-HOTEL-4C5527	2026-07-17 22:00:00.000000 UTC	2026-07-19 18:00:00.000000 UTC	"Mountain View, CA"		412.0	USD	2026-07-08 18:08:09.830528 UTC
cc32b64d-d204-4564-b8df-f7855476e718	154cec56-8ee5-4c67-922e-d66918882f99	flight	booked	sabre	SEED-FLIGHT-09C9C5	2026-07-17 08:00:00.000000 UTC	2026-07-17 12:05:00.000000 UTC	MSP-SFO		385.0	USD	2026-07-08 18:08:08.381876 UTC
```

3. Note the time, then break the flight
date -u; curl -s -X POST $URL/v1/disruption/break_flight -H 'Content-Type: application/json' -d '{"trip_id":"<TRIP_ID>"}'
Re-run the query: the flight row should read broken with a fresh updated_at.

```
Curl

curl -X 'POST' \
  'https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/disruption/break_flight' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "trip_id": "154cec56-8ee5-4c67-922e-d66918882f99"
}'
Request URL
https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/disruption/break_flight
Server response
Code	Details
200	
Response body
Download
{
  "trip_id": "154cec56-8ee5-4c67-922e-d66918882f99",
  "item_id": "cc32b64d-d204-4564-b8df-f7855476e718",
  "previous_status": "booked",
  "status": "broken",
  "affected_rows": 1
}

item_id	trip_id	type	status	provider	provider_ref	start_ts	end_ts	location	details	price	currency	updated_at
b782faa2-3f8b-4f9c-b3e2-ee39292e63a8	154cec56-8ee5-4c67-922e-d66918882f99	experience	booked	other	SEED-EXPERIENCE-4A42CD	2026-07-19 10:00:00.000000 UTC	2026-07-19 12:00:00.000000 UTC	Computer History Museum		37.5	USD	2026-07-08 18:08:13.969548 UTC
832508dc-290a-41a2-8267-c9e92db8a538	154cec56-8ee5-4c67-922e-d66918882f99	hotel	booked	sabre	SEED-HOTEL-4C5527	2026-07-17 22:00:00.000000 UTC	2026-07-19 18:00:00.000000 UTC	"Mountain View, CA"		412.0	USD	2026-07-08 18:08:09.830528 UTC
7c31c71a-86d6-4ad2-8aad-960cf84fbaa9	154cec56-8ee5-4c67-922e-d66918882f99	ground	booked	other	SEED-GROUND-6667E2	2026-07-17 12:30:00.000000 UTC	2026-07-17 13:15:00.000000 UTC	SFO -> Mountain View		58.0	USD	2026-07-08 18:08:11.444897 UTC
8fde29bb-15bd-40a9-bc94-e92d6f5d23ad	154cec56-8ee5-4c67-922e-d66918882f99	dining	booked	other	SEED-DINING-9E4288	2026-07-17 19:00:00.000000 UTC	2026-07-17 21:00:00.000000 UTC	"Castro St, Mountain View"		120.0	USD	2026-07-08 18:08:12.779509 UTC
cc32b64d-d204-4564-b8df-f7855476e718	154cec56-8ee5-4c67-922e-d66918882f99	flight	broken	sabre	SEED-FLIGHT-09C9C5	2026-07-17 08:00:00.000000 UTC	2026-07-17 12:05:00.000000 UTC	MSP-SFO		385.0	USD	2026-07-08 18:22:31.521807 UTC
```

4. Run the repair cascade
curl -s -X POST $URL/v1/sabre_tools/repair_trip -H 'Content-Type: application/json' -d '{"trip_id":"<TRIP_ID>"}'
All five completed_events should be "status": "ok". Re-run the BigQuery query and save this output — all five rows fixed with updated_at later than the step-3 time. That's the gap-2 evidence.

```
Curl

curl -X 'POST' \
  'https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/sabre_tools/repair_trip' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "trip_id": "154cec56-8ee5-4c67-922e-d66918882f99"
}'
Request URL
https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/sabre_tools/repair_trip
Server response
Code	Details
200	
Response body
Download
{
  "trip_id": "154cec56-8ee5-4c67-922e-d66918882f99",
  "session_id": "repair-8231fefef8a0",
  "launched": [
    "rebook_flight",
    "reschedule_ground",
    "move_dining",
    "shift_hotel_dates",
    "rebook_experience"
  ],
  "item_ids": [
    "cc32b64d-d204-4564-b8df-f7855476e718",
    "7c31c71a-86d6-4ad2-8aad-960cf84fbaa9",
    "8fde29bb-15bd-40a9-bc94-e92d6f5d23ad",
    "832508dc-290a-41a2-8267-c9e92db8a538",
    "b782faa2-3f8b-4f9c-b3e2-ee39292e63a8"
  ],
  "waited_for_completion": true,
  "pending_tasks": [],
  "completed_events": [
    {
      "name": "reschedule_ground",
      "status": "ok",
      "result": {
        "confirmation_ref": "GRO-6F08C0C7",
        "pickup_time": "2026-07-17T12:30:00+00:00",
        "item_status": "fixed"
      },
      "error": null,
      "started_at": "2026-07-08T18:24:45.407931+00:00",
      "finished_at": "2026-07-08T18:25:04.492464+00:00",
      "started_monotonic": 3017.084045691,
      "finished_monotonic": 3036.168589762
    },
    {
      "name": "rebook_flight",
      "status": "ok",
      "result": {
        "cancelled_ref": "SEED-FLIGHT-09C9C5",
        "confirmation_ref": "EBCCAB",
        "airline": "AA",
        "flight_number": 912,
        "departure_date": "2026-07-17",
        "departure_time": "08:00",
        "price": 187.6,
        "currency": "USD",
        "item_status": "fixed"
      },
      "error": null,
      "started_at": "2026-07-08T18:24:45.407829+00:00",
      "finished_at": "2026-07-08T18:25:05.443445+00:00",
      "started_monotonic": 3017.083945541,
      "finished_monotonic": 3037.119571168
    },
    {
      "name": "shift_hotel_dates",
      "status": "ok",
      "result": {
        "confirmation_ref": "SEED-HOTEL-4C5527",
        "hotel_name": "TRU BY HILTON MOUNTAIN VIEW",
        "check_in": "2026-07-17",
        "check_out": "2026-07-19",
        "total": "426.02",
        "currency": "USD",
        "item_status": "fixed"
      },
      "error": null,
      "started_at": "2026-07-08T18:24:45.411148+00:00",
      "finished_at": "2026-07-08T18:25:06.959946+00:00",
      "started_monotonic": 3017.087264448,
      "finished_monotonic": 3038.636071411
    },
    {
      "name": "move_dining",
      "status": "ok",
      "result": {
        "confirmation_ref": "DIN-76B9D89A",
        "reservation_time": "2026-07-17T19:00:00+00:00",
        "item_status": "fixed"
      },
      "error": null,
      "started_at": "2026-07-08T18:24:45.409450+00:00",
      "finished_at": "2026-07-08T18:25:07.998214+00:00",
      "started_monotonic": 3017.085566299,
      "finished_monotonic": 3039.674336197
    },
    {
      "name": "rebook_experience",
      "status": "ok",
      "result": {
        "confirmation_ref": "EXP-A26B7068",
        "date": "2026-07-19",
        "item_status": "fixed"
      },
      "error": null,
      "started_at": "2026-07-08T18:24:45.414469+00:00",
      "finished_at": "2026-07-08T18:25:19.979449+00:00",
      "started_monotonic": 3017.090585177,
      "finished_monotonic": 3051.655574865
    }
  ]
}
Response headers
item_id	trip_id	type	status	provider	provider_ref	start_ts	end_ts	location	details	price	currency	updated_at
7c31c71a-86d6-4ad2-8aad-960cf84fbaa9	154cec56-8ee5-4c67-922e-d66918882f99	ground	fixed	other	SEED-GROUND-6667E2	2026-07-17 12:30:00.000000 UTC	2026-07-17 13:15:00.000000 UTC	SFO -> Mountain View		58.0	USD	2026-07-08 18:25:03.270496 UTC
8fde29bb-15bd-40a9-bc94-e92d6f5d23ad	154cec56-8ee5-4c67-922e-d66918882f99	dining	fixed	other	SEED-DINING-9E4288	2026-07-17 19:00:00.000000 UTC	2026-07-17 21:00:00.000000 UTC	"Castro St, Mountain View"		120.0	USD	2026-07-08 18:25:06.961236 UTC
cc32b64d-d204-4564-b8df-f7855476e718	154cec56-8ee5-4c67-922e-d66918882f99	flight	fixed	sabre	SEED-FLIGHT-09C9C5	2026-07-17 08:00:00.000000 UTC	2026-07-17 12:05:00.000000 UTC	MSP-SFO		385.0	USD	2026-07-08 18:25:04.390053 UTC
832508dc-290a-41a2-8267-c9e92db8a538	154cec56-8ee5-4c67-922e-d66918882f99	hotel	fixed	sabre	SEED-HOTEL-4C5527	2026-07-17 22:00:00.000000 UTC	2026-07-19 18:00:00.000000 UTC	"Mountain View, CA"		412.0	USD	2026-07-08 18:25:05.570686 UTC
b782faa2-3f8b-4f9c-b3e2-ee39292e63a8	154cec56-8ee5-4c67-922e-d66918882f99	experience	fixed	other	SEED-EXPERIENCE-4A42CD	2026-07-19 10:00:00.000000 UTC	2026-07-19 12:00:00.000000 UTC	Computer History Museum		37.5	USD	2026-07-08 18:25:18.889218 UTC
```

5. Prove the event-day fallback (env-var change — yours to run):
gcloud run services update vocal-bridge-be-dev --region us-west1 --update-env-vars SABRE_MODE=real
Break and repair the trip once more (steps 3–4) — it should still succeed, and the logs should show the fallback warning:
gcloud run services logs read vocal-bridge-be-dev --region us-west1 --limit 50 | grep -i "falling back"
Then flip back with --update-env-vars SABRE_MODE=mock.

```passed```

6. Edge cases
- Call break_flight twice with the same trip_id → second call is a clean re-flip, not a 500.
- Call it with {"trip_id":"nope"} → 404, no write.
```passed```

7. Tone check — skim sabre-api-notes.md, the tool docstrings in backend/api/repair_tools.py, and the endpoint responses: plain engineering prose, no marketing.
```passed```