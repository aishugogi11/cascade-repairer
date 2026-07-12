# Plan — Pacific-time discipline & pin the displayed trip

Task groups are independently implementable; 1–2 (backend) unblock 3–4 (surfaces).
Group 5 lands alongside whichever group it asserts on.

## 1. Backend ingest — declare mock times Pacific wall-clock

1.1. `backend/api/concierge.py`: in `_booking_writes`, build the flight item's
     `start_ts`/`end_ts` with `tzinfo=ZoneInfo("America/Los_Angeles")` instead of
     `timezone.utc` (`ZoneInfo` is already imported for the Phase 18 today-line).
1.2. `backend/api/concierge.py`: same change in `_completion_items`' `ts()` helper.
1.3. `backend/api/sabre_tools.py`: same change across all five `_SEED_ITEMS`
     entries (import `ZoneInfo`; consider a module-level `_PACIFIC = ZoneInfo(...)`
     constant per file to avoid repetition — match local style, no new helper module).

## 2. Backend pin seam — optional trip_id through /query

2.1. `backend/api/web_call.py`: add `trip_id: Optional[str] = None` to
     `QueryRequest` (strip/normalize blank → `None`); pass it through
     `delegated_query` → `answer_query(session_name, query, trip_id)`.
2.2. `backend/api/web_call.py`: extend the `answer_query` seam function's signature
     with `trip_id: Optional[str] = None`, forwarding to
     `concierge.answer_query` (keep it the single stable patch point).
2.3. `backend/api/concierge.py`: `answer_query` accepts `trip_id: Optional[str] = None`
     and passes it to `ensure_trip_context(session_name, trip_id=trip_id)`. No change
     inside `ensure_trip_context` — its cache-first order already gives
     pin-only-if-unpinned.

## 3. Web pages

3.1. `backend/api/assets/itinerary/page.html`: add `timeZone: 'America/Los_Angeles'`
     to the item-card `toLocaleString` opts and the repair-feed
     `toLocaleTimeString`; append a “PT” label to displayed times.
3.2. `backend/api/assets/demo/page.html`: same two changes (card times + feed clock).
3.3. `backend/api/web_call.py` page template: read `trip_id` from the URL query
     string into a JS variable, expose `window.vbSetTrip(tripId)` to update it, and
     include it (when set) in the `/v1/web_call/query` POST body.
3.4. `backend/api/mobile_voice.py` page template: same as 3.3 (keep the two pages'
     delegation blocks aligned, as today).
3.5. `backend/api/mobile_voice.py` **temporary page bridge** (mobile page only —
     not web_call): on load, fetch `GET /v1/sabre_tools/latest_trip_id` with the
     page's existing access-code headers and hold the result as the lowest-
     precedence `trip_id` source (`vbSetTrip` → `?trip_id=` → fetched latest); a
     failed fetch omits `trip_id` and never blocks connecting. Comment it as
     `TEMP bridge for the in-review binary — remove when native vbSetTrip ships
     (v1.0.1)`.

## 4. iOS — tell the voice session what's on screen

4.1. `APIConfig.mobileVoiceURL`: add `tripId: String?`, appended as a `trip_id`
     query item; `VoiceWebView` passes the currently displayed trip when building
     the URL.
4.2. `VoiceManager`: add a `setTrip(_ tripId: String)` that runs
     `window.vbSetTrip && window.vbSetTrip('<id>')` via `evaluateJavaScript`;
     wire it so any change to `TripManager`'s displayed trip (cold-start
     resolution landing, long-press selector) forwards the id. This closes the
     race where the webview loads before `latest_trip_id` resolves.
4.3. Verify (no code expected): no view renders `start_ts`/`end_ts` or any
     wall-clock time device-local — confirm the requirements audit and note the
     result in the PR description.

## 5. Tests (`backend/tests/`)

5.1. Ingest conversion: `_booking_writes`' item (mocked repos) for a `06:15`
     July departure has `start_ts.astimezone(timezone.utc)` at `13:15` UTC
     (PDT = UTC−7); same-style assertion for `_completion_items` and one
     `_SEED_ITEMS` entry.
5.2. Pin threading: `answer_query(session, query, trip_id=…)` with a non-empty
     mocked trips table pins that trip (agent instructions carry its summary).
5.3. No-clobber: a session pinned to trip A, then queried with `trip_id=B`,
     stays pinned to A.
5.4. Unpinned default preserved: `answer_query` without `trip_id` still reaches
     `search_flights` — the Phase 18 regression test must stay green as-is.
5.5. `/v1/web_call/query` endpoint: accepts a body with `trip_id`, forwards it to
     the `answer_query` seam (patch the seam, assert the argument); a body without
     `trip_id` behaves exactly as before.
