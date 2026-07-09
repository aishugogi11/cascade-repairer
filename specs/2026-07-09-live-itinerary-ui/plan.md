# Plan — Live Itinerary UI (Phase 10)

Task groups are independently implementable in order; each leaves the suite
green.

## 1. Data layer

1.1 Add `list_recent_trips(limit: int = 10)` to
    `backend/api/repositories/trips.py` — `SELECT * FROM trips ORDER BY
    created_at DESC LIMIT @limit`, returning the standard
    `(success, [Trip], error)` tuple shape used by the other repo functions.

1.2 Unit tests in `backend/tests/test_repositories.py` following the existing
    mocked-`run_select` pattern: happy path, empty result, helper error.

## 2. Status & trips endpoints

2.1 Create `backend/api/itinerary_ui.py` with router `itinerary_ui`
    (module-level `APIRouter()` named like the other routers).

2.2 `GET /status/{trip_id}` — `async def`; `asyncio.to_thread` around
    `trips.get_trip` and `itinerary_items.list_items_for_trip`; 404 for an
    unknown trip; response = `trip`, `items[]` (sorted by `start_ts`),
    computed `summary` (per-status counts + `all_clear`), `fetched_at`.

2.3 `GET /trips` — `async def` + `to_thread` around `list_recent_trips`;
    returns trip_id, title, status, dates per trip for the selector.

2.4 Register the router in `backend/main.py` under `/v1/itinerary`,
    tags `["itinerary"]`, matching the existing include_router blocks.

2.5 Endpoint tests `backend/tests/test_itinerary_ui.py` (hermetic, repos
    mocked): status happy path incl. summary math and item sort, unknown trip
    404, repo-error path, trips list.

## 3. Page & serving

3.1 Create `backend/api/assets/itinerary/page.html` — single self-contained
    file (inline CSS/JS, no external requests): header with trip title +
    status banner, itinerary timeline/cards region, event-feed rail,
    timer slot, trip-selector control. Layout adapted from
    `about/ui_ideas/ui_mockup_2026_07_09.png` (timeline + feed portions).

3.2 In `itinerary_ui.py`: read the file once at import; `GET /` returns it
    via `HTMLResponse` (same shape as `web_call_page`).

3.3 Test: `GET /v1/itinerary/` returns 200, `text/html`, and contains the
    page title marker.

## 4. Live behaviour (JS)

4.1 Poll loop: fetch `status/{trip_id}` every 1.5 s; render the five cards
    with status chip + color class; animate class changes
    (broken red / repairing amber-pulse / fixed green / booked-planned blue /
    cancelled gray). Show a staleness note if a poll fails; keep polling.

4.2 Event feed: diff statuses vs. the previous poll; append one entry per
    transition ("Flight — broken → repairing") timestamped from `updated_at`;
    newest first.

4.3 Elapsed timer: start on first observed `broken`; tick client-side; freeze
    when `summary.all_clear` returns true; style against the 60 s target
    (e.g. green under 60 s).

4.4 Trip selector: populate from `GET /trips`; default to `?trip_id=` query
    param, else the most recent trip; switching trips resets feed and timer.

## 5. Validation pass

5.1 Full suite green: `cd backend && python -m pytest`.

5.2 Manual demo-loop walkthrough per `validation.md` (seed → break → repair
    while watching the page), locally via `make backend`, then on Cloud Run
    after merge.

5.3 Tone check of all on-screen copy against requirements Context rules.
