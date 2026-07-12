# Validation — Voice Booking Page (Phase 21)

## Automated

```bash
docker compose exec -T backend python -m pytest tests/ -q
```

All tests pass (289+ currently green; no regressions). Specific assertions
required:

- `search_flights_impl` records the latest-search slot; `book_flight_impl`
  clears it on success.
- `GET /v1/itinerary/status/{trip_id}` carries `pending_options` when the
  slot's session is pinned to that trip, and when the slot's session is
  unpinned.
- The block is **omitted** when: the slot is empty; the slot's session is
  pinned to a different trip; reading the slot raises (poll still returns a
  valid payload — the `detail` best-effort standard).
- Existing status-payload consumers are untouched: `trip`, `items`,
  `summary`, `fetched_at`, and `detail` assertions all still pass unchanged
  (additive-only contract).
- `GET /v1/booking/` returns the page shell without an access code
  (allowlisted); gated JSON endpoints under `/v1/` still 401 without
  `X-Access-Code` when `DEMO_ACCESS_CODE` is set.
- Tests are hermetic: no GCP credentials, no `OPENAI_API_KEY`.

## Manual (scripted QA — no browser-automation dependency, standing decision)

Walkthrough, in `SABRE_MODE=mock` against local compose (or the deployed
service), page open at `/v1/booking/?code=…`:

1. **Cold start**: with no `?trip_id=`, the page shows the awaiting state and a
   populated recent-trips selector (PT labels, newest-first). Picking a trip
   renders its cards.
2. **Candidates appear**: drive the guided flow via the curl rehearsal path on
   `POST /v1/web_call/query` (no outbound-call quota): ask for flights. Within
   ~1.5 s the candidate panel shows the three deterministic mock options —
   numbered, PT times, rounded prices, no airline codes — matching what the
   Concierge's reply speaks.
3. **Booking hands off**: book option N via the `/query` seam. The candidate
   panel clears and the current flight card appears (via `latest_trip_id`
   re-resolution — no page reload) showing the chosen option; `detail` fields
   render when present.
4. **Reservation materializes**: after `complete_trip`, hotel, ground, dining,
   and experience cards land one by one across successive polls.
5. **Pinning contract**: `?trip_id=` seeds the displayed trip;
   `window.vbSetTrip('<id>')` in the console repoints the poll.
6. **Edge cases**: unknown `trip_id` → graceful empty/awaiting state, poll
   keeps running; access code absent → page shell loads but fetches fail
   quietly to the gate; a second search mid-conversation replaces the panel
   contents; killing the backend mid-poll → page recovers on restart without
   reload.

## Design check

Side-by-side with `about/ui_ideas/ui_mockup_2026_07_09.png`:

- The page reads as the same product as the mockup — header (product name,
  current-traveler, status pill), left rail (traveler context, trip timeline
  with status icons, collapsible Recent Trips), card/pill/color language.
- The candidates panel visually matches the mockup's "AI Recommended" option
  card treatment.
- Voice-column and repair surfaces (orb, conversation feed, Sabre log,
  recovery banner/timer, downstream impact) are deliberately absent — they
  are Phases 22–23; their space must not leave broken-looking gaps.

## Tone check

- Times labeled "PT" everywhere (never "PST", never browser-local).
- Prices rounded as the Concierge speaks them; no airline codes in headline
  copy.
- Copy is traveler-voiced, stage-readable (large type, high contrast on a
  projector).

## Definition of done

- Automated suite green with the assertions above.
- Manual walkthrough steps 1–6 pass in `SABRE_MODE=mock` locally.
- The pre-disruption beat works end to end on one screen: candidates visible
  while the voice conversation discusses them, then the full five-item
  reservation on screen — before any disruption is triggered.
- `specs/tech-stack.md` updated; Phase 21 marked `[x] COMPLETE` in
  `specs/roadmap.md`.
