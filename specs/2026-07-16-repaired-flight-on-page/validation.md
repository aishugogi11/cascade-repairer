# Validation — Repaired flight reflected on the cascade page (Phase 32)

## Automated

Run inside the container (host Python is not the test environment):

```
docker compose exec backend python -m pytest
```

- The full bare suite passes (405+ tests as of Phase 29; no new failures, no new
  `RuntimeWarning`s added by this phase).
- Specific assertions that must exist and pass:
  1. `itinerary_items.update_flight_fields` issues parameterized DML (not streaming),
     refreshes `updated_at`, and surfaces failure/0-row through its return tuple.
  2. After `_rebook_flight` completes, the flight item's `start_ts`/`end_ts` equal
     the chosen option's PT-localized instants (red-eye case included: an arrival
     with `arrive_date` on the next PT day yields `end_ts > start_ts`),
     `price`/`currency` equal the chosen fare, and `details.airline`/
     `details.flight_number` are the **rebooked** flight's identity.
  3. A failed/0-row field update makes `_rebook_flight` raise — the cascade unit
     reports `error` rather than flipping `fixed` over stale fields.
  4. The mock-fallback path (empty real re-shop) updates the item row from the
     mock-chosen option identically.
  5. `_rebook_flight` with no original-flight context (walkthrough shape, all
     optional params omitted) still succeeds; `rebooked_from` degrades gracefully.
  6. `_flight_repair_detail` returns a `rebooked_from` string with full context,
     a times/price-only string without identity, omits the key with nothing usable,
     and never raises; `voice_guided_booking` and seeded detail outputs unchanged.
  7. Existing Phase 31 exclusion-filter tests still green (the re-stamped identity
     is what the second re-shop excludes).

## Manual

Scripted walkthrough, locally in mock mode (`make up`, `SABRE_MODE` unset):

1. `POST /v1/sabre_tools/seed_trip` → open `GET /v1/cascade/?code=…` → the seeded
   trip renders; note the flight card's times and price.
2. `POST /v1/disruption/break_flight` for the trip → card goes `broken` (red).
3. `POST /v1/sabre_tools/repair_trip` → within a poll or two the card flips
   `repairing` → `fixed`, and — the acceptance moment — **the card now shows the
   rebooked flight's times and price, not the original's**, with the original
   visible as a struck-through "was …" line.
4. Second break → repair on the same trip: the new repair excludes the *current*
   (rebooked) flight — the flight changes again (identity re-stamp working).
5. Edge: a seed trip with no stamped identity still repairs; the was-line shows
   times/price only or is absent — the page never errors (check the console).
6. The repair feed timestamps read sensibly (fresh `updated_at`), all clocks
   labeled "PT".
7. Booking page spot-check (`GET /v1/booking/`): its current-flight card also shows
   the rebooked flight (inherited from the corrected row); nothing broken by the
   additive detail field.

Then on Cloud Run after the PR merges (deployed by the `vb/dev` push trigger):
repeat steps 1–3 against the live service (walkthrough seams only — no outbound
calls, no quota). The full voice rerun stays the operator run-sheet path and is
not required to close this phase.

## Tone check

The was-line is user-facing copy: plain and glanceable, matches the detail panel's
register ("Was UA 512 · departed 8:05 AM PT · $214" — rounded prices, PT-labeled
clocks, no jargon; airline *codes* are acceptable here only until Phase 33 lands
names). No exclamation marks, no system-speak ("row updated").

## Definition of done

- [ ] A. The cascade page shows the rebooked flight (times, price) with the
      old → new treatment after a repair — verified by the mock walkthrough locally
      **and** on the deployed service.
- [ ] B. PR into `vb/dev` carries the pre-merge evidence sections
      (`### Mock walkthrough` / `### Live run` / `### Pytest`) with placeholders
      replaced (`PR_BODY.md` + `git_pull_dev.sh`).
- [ ] C. Full bare suite green in the container; the seven assertions above exist.
- [ ] D. No changes to consent flow, repair guarantee, voice scripts, trip model,
      or schema; no new dependencies.
- [ ] E. Phase 32 marked `[x] COMPLETE` in `specs/roadmap.md`.
