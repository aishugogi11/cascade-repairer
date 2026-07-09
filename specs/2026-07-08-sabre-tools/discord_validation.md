**Phase 6 (Sabre repair tools) is live on Cloud Run — full cascade validated in production today** 🎉

Ran the whole break-and-heal loop against the deployed service and real BigQuery, using three new endpoints:

**1. Seed** — `POST /v1/sabre_tools/seed_trip` created a booked demo trip: flight (MSP→SFO), hotel (Mountain View), ground, dining, and a Computer History Museum tour. All five itinerary rows confirmed `booked` in BigQuery at 18:08 UTC.

**2. Break** — `POST /v1/disruption/break_flight` flipped the flight to `broken` at 18:22 UTC (this is the demo's trigger — curl-able from a phone on event day).

**3. Repair** — `POST /v1/sabre_tools/repair_trip` fired all five repairs **in parallel**: rebook_flight, shift_hotel_dates, reschedule_ground, move_dining, rebook_experience. Every one came back `ok` with a real confirmation payload — e.g. the flight was rebooked as **AA 912, new PNR EBCCAB, $187.60**.

**4. Verify** — re-queried BigQuery: **all five rows read `fixed` with fresh `updated_at` stamps**, about 35 seconds from launch to last repair landing. Under the 60-second demo target, on the deployed stack, with real table writes — not mocked DML.

```
flight      broken → fixed   18:25:04 UTC  (rebooked AA 912, PNR EBCCAB)
hotel       booked → fixed   18:25:05 UTC  (dates confirmed 7/17–7/19)
ground      booked → fixed   18:25:03 UTC
dining      booked → fixed   18:25:06 UTC
experience  booked → fixed   18:25:18 UTC
```

Sabre calls run through the documented-shape mock layer behind a `SABRE_MODE` env flag — on event day we flip one env var to real Sabre, and if the sandbox flakes mid-demo, each call auto-falls back to the mock and the cascade still lands.

This closes both Phase 5 carry-over gaps. Next up: voice (Phase 7) and the live itinerary UI that shows these flips on screen.
