# Phase 22 — Validation

How we verify the Cascade dashboard repair surfaces are done. Automated checks
must pass in the container; manual checks walk the page in `SABRE_MODE=mock`
(no outbound-call quota spent — rehearsal path is `/v1/web_call/` + curl, and
the dashboard reads only the status poll).

## Automated

Run the bare suite inside the built container (hermetic — no GCP creds, no
network, `cert` deselected):

```
docker compose exec <api-service> pytest -q          # -m "not cert" via addopts
```

Assertions required:

1. **Suite green.** The full bare suite passes (current baseline: 405 passed —
   the new tests add to it; no regressions).
2. **`test_cascade_ui.py`** — `GET /v1/cascade/` returns **200** + `text/html`;
   the shell is self-contained (no external `http(s)://` asset references); it
   carries the access-code and status-poll wiring markers **and both trigger
   targets (`/v1/demo/book`, `/v1/demo/disrupt`) in the markup** (mirrors
   `test_booking_ui.py`). The test asserts wiring only — it never calls the
   `/v1/demo` endpoints (those place real calls / need env; already covered by
   `test_demo.py`).
3. **`test_access_gate.py`** — `/v1/cascade/` is reachable **without** an
   `X-Access-Code` header (page-shell allowlist), alongside the other four
   shells; gated JSON APIs still 401 without the header.
4. **`test_concierge.py` item-H cases** —
   a. a fresh `_LATEST_SEARCH` slot still surfaces via
      `pending_options_for_trip` (pinned-to-trip and unpinned);
   b. a slot older than `_LATEST_SEARCH_TTL` returns `None`;
   c. the pinned/unpinned resolution is unchanged for a fresh slot.
5. **No new endpoint / no schema change** — grep confirms the page consumes only
   `GET /v1/itinerary/status/{trip_id}`, `GET /v1/itinerary/trips`,
   `GET /v1/sabre_tools/latest_trip_id`; no new route besides the `GET /v1/cascade/`
   shell; `itinerary_ui.py`'s status payload gains no field.
6. **`/v1/booking/` untouched** — `git diff` shows no change to
   `backend/api/assets/booking/page.html` or `backend/api/booking_ui.py`.

## Manual (scripted QA)

**Two ways to walk it.** For silent visual rehearsal (no quota), seed/break/
repair via the existing seams by hand (`POST /v1/sabre_tools/seed_trip`,
`POST /v1/disruption/break_flight` / `POST /v1/sabre_tools/repair_trip`) and
watch `GET /v1/cascade/?trip_id=<id>&code=<code>`. For the **real end-to-end
demo** (costs ~2 VB calls, needs the call env set — Cloud Run), drive it
**entirely from the page's trigger controls** — this is the acceptance path for
"one page, no bouncing":

0. **Single-page trigger loop** — open `GET /v1/cascade/?code=<code>` with **no**
   `trip_id`, click **Book** (phone rings, trip books), the booked trip appears
   on the page without reload or navigation, then click **Cancel flight →
   cascade** and watch the repair surfaces resolve — all without leaving the
   page or opening `/v1/booking/` or `/v1/demo/`. Locally (env unset) the
   controls surface a clean **503** instead of crashing.

1. **Frame renders** — app header + status pill, left rail (traveler context,
   trip timeline with per-leg icons, collapsible recent trips), current-flight
   card, four reservation cards, right recommendation column — matching the
   mockup's layout and the shipped `/v1/booking/` frame.
2. **Recovery banner** appears while a leg is broken/repairing with the mockup's
   copy, and resolves to all-clear when every leg is fixed.
3. **Recovery timer** counts against the 60-second target from the first
   observed break and settles on all-clear (client-side; no server event state).
4. **Status treatments** — the current-flight card, reservation cards, and
   timeline legs visibly move **broken → repairing → fixed** as the 1.5 s poll
   picks up status flips (all six lifecycle statuses have a visual hook).
5. **Disruption score** chip shows a value · band, is higher while legs are
   broken, and drops toward Minimal as the trip heals — visibly derived from
   real state, not static.
6. **Downstream-impact panel** lists one glanceable line per affected leg from
   the `detail` payload with an OK / Adjusted dot; legs without `detail` are
   omitted, not shown blank.
7. **Center placeholder** — the center column shows the clearly-labeled
   "Phase 23" voice placeholder; no orb, no mic, no network activity for voice.
8. **Pinning / trip switching** — `?trip_id=` pins; a trip booked mid-session
   (via `latest_trip_id`) appears within ~4 s without reload; recent-trips
   selector repoints the poll.
9. **Item-H behavior** — after a guided-booking conversation surfaces flight
   options and is then abandoned (no booking, no further search), the
   `pending_options` candidates stop appearing on the poll once the TTL passes
   (verify via the status endpoint JSON or the panel disappearing).

## Tone check

- Banner, downstream-impact lines, and any repair-feed copy read in the
  mockup's glanceable, traveler-voiced register (`about/ui_ideas/
  ui_mockup_2026_07_09.png`) — short, plain, no jargon dumped on the traveler.
- Any clock time rendered is `America/Los_Angeles`, labeled **PT** (never PST) —
  the Phase 19 discipline.

## Definition of done

- [ ] `GET /v1/cascade/` is the **single consolidated demo surface**: shows the
      booking beat and the repair beat, and the whole demo (book → cancel →
      cascade → fixed) runs on it with **no navigation to another page**.
- [ ] Cloned frame + all four repair surfaces (banner + 60 s timer,
      broken→repairing→fixed treatments, disruption score, downstream-impact
      panel) driven only by the existing polls.
- [ ] On-page **Book** and **Cancel flight → cascade** controls fire
      `/v1/demo/book` / `/v1/demo/disrupt`; Book pins the returned trip
      immediately; 503/502 surface cleanly (no crash).
- [ ] Center voice column is a labeled Phase 23 placeholder; no voice wiring.
- [ ] Item-H age-expiry lands in `pending_options_for_trip` with tests.
- [ ] `/v1/cascade/` on the access-gate allowlist; `/v1/booking/` unchanged.
- [ ] Full bare suite green in the container; new unit tests included.
- [ ] Manual mock-mode walkthrough passes 1–9 above.
- [ ] PR description carries the surface summary + mock-mode broken→fixed
      evidence **pre-merge** (`pr-evidence-guard`).
- [ ] Phase 22 marked `[x] COMPLETE` in `specs/roadmap.md` after validation.
