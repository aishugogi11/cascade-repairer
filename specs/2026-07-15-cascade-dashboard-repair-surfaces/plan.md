# Phase 22 — Implementation plan

Build order: back-end plumbing first (router + gate + the item-H hardening,
all unit-testable and hermetic), then the page, then the repair surfaces on it,
then tests. Each group is independently landable.

## 1. Backend: new page router + access gate

1.1 Create `backend/api/cascade_ui.py` — thin router cloned from
    `backend/api/booking_ui.py`: `cascade_ui = APIRouter()`, one
    `GET /` → `HTMLResponse` reading `assets/cascade/page.html` per request.
    Docstring names it the Phase 22 repair-beat surface and states it is
    driven only by the existing status/trips/latest_trip_id endpoints.

1.2 Register it in `backend/main.py` — import `cascade_ui`, `app.include_router(
    cascade_ui, prefix="/v1/cascade", tags=["cascade"])`, next to `booking_ui`.

1.3 Add `"/v1/cascade"` to the access-gate allowlist in
    `backend/api/access_gate.py` (the page-shell group with `/v1/booking`,
    `/v1/itinerary`, etc.) — the shell is inert without the gated JSON APIs.

## 2. Backend: `_LATEST_SEARCH` age-expiry hardening (item H)

2.1 In `backend/api/concierge.py`, add a documented module-level TTL constant
    near `_LATEST_SEARCH` (e.g. `_LATEST_SEARCH_TTL = timedelta(minutes=10)` —
    pick a window comfortably longer than a real guided-booking turn but short
    enough that an abandoned conversation clears within the demo; document the
    reasoning in a comment).

2.2 In `pending_options_for_trip`, before returning the block, compute the
    slot's age from `slot.recorded_at` vs `datetime.now(timezone.utc)` and
    return `None` when it exceeds the TTL — so an abandoned search stops
    surfacing on the poll. Keep it additive and best-effort: no exception path,
    no change to the pinned/unpinned logic already there.

2.3 (Optional, only if trivial) clear the expired slot on read to avoid
    re-checking age every poll — guarded like the existing ownership clears so
    it never wipes another session's in-flight slot. If it adds complexity,
    leave the slot and rely on the read-time filter; the visible effect is
    identical.

## 3. Page shell: clone the booking frame

3.1 Copy `backend/api/assets/booking/page.html` to
    `backend/api/assets/cascade/page.html` as the starting point — same
    self-contained structure, `?code=`/`localStorage`/`X-Access-Code` handling,
    `?trip_id=`/`window.vbSetTrip()` pinning, 1.5 s status poll, 4 s
    `latest_trip_id` re-resolve adopting a change, `<title>`/header updated to
    the Cascade repair-beat identity.

3.2 Lay out the three-column grid from the mockup: left rail (traveler context,
    trip timeline, recent trips — already present in the clone), **center
    column** (Phase 22: voice placeholder — group 7), right column
    (recommendation panel — extended in group 5), plus the operator trigger
    controls (group 6). The page must read as one screen showing both the
    booking beat and the repair beat.

## 4. Repair surfaces: banner, timer, status treatments

4.1 **Recovery banner** — a top banner shown while any item is `broken` or
    `repairing` (derive from `summary.counts` / item statuses), in the mockup's
    treatment and copy; resolves to an all-clear state when `summary.all_clear`.

4.2 **Recovery timer** — port the itinerary page's client-side 60-second
    recovery timer (start on first observed `broken`/`repairing`, count against
    the 60 s target, stop/settle on all-clear). No server-side event state.

4.3 **broken → repairing → fixed treatments** — status classes on the
    current-flight card, the four reservation cards, and each trip-timeline leg
    covering all six lifecycle statuses; the mockup's red / in-progress / green
    register. Reuse the itinerary page's between-poll status-diff to animate
    transitions and feed a lightweight repair feed if it fits the layout
    (feed detail is Phase 23's conversation column — keep this minimal).

## 5. Disruption score + downstream-impact panel (right column)

5.1 **Disruption score chip** — compute a 0–100 score + band (Minimal /
    Moderate / Severe) in page JS from the status payload. Documented heuristic,
    e.g.: base on the count of `broken`/`repairing` legs, add weight from
    `detail.price_delta` where present, and from elapsed-vs-60 s; clamp to
    0–100; map bands by threshold. Reads Minimal / low when `all_clear`. Comment
    the formula so it's explainable to a judge. Render in the mockup's chip
    treatment (value · band, with the progress bar).

5.2 **Downstream-impact panel** — under the recommendation card, render one
    glanceable line per affected leg from the existing `detail` payload
    (`impact` sentence + an OK / Adjusted status dot keyed off `price_delta`
    "$0" vs a real delta). Omit legs with no `detail` (best-effort, mirrors the
    iOS static fallback). Keep copy in the mockup's register.

## 6. On-page trigger controls (both beats — real-call path)

6.1 Add two controls to the page (mockup register; a compact operator control
    cluster, e.g. in the header or a corner of the center column so they don't
    fight the repair surfaces). Clone the fetch/disabled-state/error-surfacing
    JS from the shipped `backend/api/assets/demo/page.html` — same
    `X-Access-Code` header the page already attaches, same scrub of any error.

6.2 **"Book"** → `POST /v1/demo/book` with `{user_id, title}` (defaults are
    fine — `BookRequest` defaults them). On success, read `trip_id` from the
    response and **pin it immediately** (set the poll target / `window.vbSetTrip`
    equivalent) so the seeded trip renders without waiting on the 4 s
    `latest_trip_id` re-resolve. Disable the button while in flight
    (`place_call` blocks ~10–16 s).

6.3 **"Cancel flight → cascade"** → `POST /v1/demo/disrupt` with `{trip_id}` =
    the currently-pinned trip; disable until a trip is pinned. On success the
    1.5 s poll picks up the broken flight and the cascade, driving groups 4/5.

6.4 Surface the **503** (env unset) and **502** (call failed) responses as a
    small inline status, not a crash — locally the controls will 503; that's
    expected and must read cleanly. Never render the callee number or any
    scrubbed field (the orchestrator already scrubs; don't reintroduce it).

## 7. Center voice-column placeholder

7.1 Render a static, clearly-labeled placeholder card in the center column
    ("Voice — Phase 23" or similar) sized to hold the eventual orb/feed, so the
    three-column layout matches the mockup and Phase 23 replaces this block
    with the live voice surfaces without a relayout. No VB CDN imports, no
    token fetch, no event handlers.

## 8. Tests (hermetic, in-container)

8.1 `backend/tests/test_cascade_ui.py` — `GET /v1/cascade/` returns 200 + HTML,
    the shell is self-contained (no external `http(s)://` asset refs beyond
    allowed inline data), and it carries the access-code / poll wiring markers
    plus the two trigger-control targets (`/v1/demo/book`, `/v1/demo/disrupt`
    present in the markup) — mirror `test_booking_ui.py`'s assertions. **Do
    not** call the `/v1/demo` endpoints for real here (they place calls / need
    env) — assert the shell wiring only; the orchestrator itself is already
    covered by `test_demo.py`.

8.2 Extend `backend/tests/test_access_gate.py` — add `/v1/cascade/` to the
    shell allowlist cases (public without a header; the pattern already lists
    the other four shells).

8.3 Extend `backend/tests/test_concierge.py` — add item-H coverage:
    - a fresh slot (recent `recorded_at`) still surfaces via
      `pending_options_for_trip`;
    - a slot older than the TTL returns `None` (monkeypatch `recorded_at` or
      the TTL / clock seam — follow the module's existing time handling);
    - the existing pinned/unpinned behavior is unaffected for a fresh slot.

8.4 Run the full bare suite (`-m "not cert"`) green in the container before PR.

## 9. Docs / spec bookkeeping

9.1 Mark **Phase 22 `[x] COMPLETE`** in `specs/roadmap.md` only after
    validation passes (per SDD flow; not part of the code change itself).
9.2 Note in the PR description (pre-merge, per the `pr-evidence-guard` workflow)
    the new consolidated `/v1/cascade/` surface + trigger controls, the item-H
    hardening, and a mock-mode walkthrough screenshot/notes of the on-page
    Book → Cancel → broken → repairing → fixed run.
