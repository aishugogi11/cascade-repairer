# Validation — Live Itinerary UI (Phase 10)

## Automated

- `cd backend && python -m pytest` passes with no GCP credentials and no
  `OPENAI_API_KEY` set (hermetic), locally and inside the CI container.
- Specific assertions that must exist and pass:
  - `list_recent_trips` returns trips ordered newest-first; empty and
    helper-error paths covered (`test_repositories.py`).
  - `GET /v1/itinerary/status/{trip_id}`: 200 with `trip`, `items` sorted by
    `start_ts`, `summary` counts that add up to `len(items)`, and correct
    `all_clear` (true only when no item is broken/repairing); 404 on unknown
    trip; 5xx/error body on repository failure (`test_itinerary_ui.py`).
  - `GET /v1/itinerary/trips`: 200 with the selector fields.
  - `GET /v1/itinerary/`: 200, `text/html`, page marker present.
- No new Python or JS dependencies introduced (requirements files and page
  `<script>`/`<link>` tags unchanged from repo conventions — the page makes
  no external requests).

## Manual

Walkthrough (locally via `make backend`, then repeated on the deployed
Cloud Run service after merge):

1. `POST /v1/sabre_tools/seed_trip` — note the returned `trip_id`.
2. Open `/v1/itinerary/` — the seeded trip loads by default; five cards render
   (flight, hotel, ground, dining, experience), all `booked` blue; timer idle;
   feed empty; selector lists the trip.
3. `POST /v1/disruption/break_flight` — within ~2 s the flight card flips red,
   the feed logs the break, the timer starts.
4. `POST /v1/sabre_tools/repair_trip` — cards flip to amber `repairing` then
   green `fixed` as repairs land, each transition appearing in the feed; timer
   freezes when the last item fixes; total under 60 s.
5. Read-back: statuses on screen match `itinerary_items` rows in BigQuery
   (fresh `updated_at`).

Behaviour and edge cases:

- Unknown `?trip_id=` shows a friendly not-found state, not a blank page or
  console error.
- Kill the backend mid-poll: the page shows a staleness/reconnecting note and
  recovers when the backend returns.
- Switching trips in the selector resets the feed and timer and renders the
  new trip's items.
- A `cancelled` item renders in the muted style (all six statuses have a
  visual).
- Page is readable from across a room at projector distance: status colors
  distinguishable, card text legible at arm's length from a laptop ~3 m away.

## Tone check

All user-visible copy (banner, feed entries, empty/error states) is
traveler-facing: calm, present tense, reassuring; no exclamation points; no
internal jargon (no "row", "DML", "poll", "endpoint"). Feed entries read like
the mockup's voice ("Rebooking your flight", "Hotel confirmed — no change
needed"), not like log lines.

## Definition of done

- All automated assertions above pass in CI (pytest inside the built image).
- The manual walkthrough runs clean on the deployed Cloud Run service with
  the screen flipping broken → repairing → fixed live.
- Tone check passed.
- Phase 10 marked `[x] COMPLETE` in `specs/roadmap.md`.
