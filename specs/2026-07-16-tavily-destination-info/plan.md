# Plan — Phase 35: Tavily destination-info tool for the Concierge

Task groups are independently implementable in order. All code lands in
`backend/api/concierge.py` plus one deps line and tests — nothing else moves.

## 1. Dependency

1.1 Add `tavily-python` (pinned to the current release) to
    `backend/requirements.txt`.
1.2 Rebuild the local container (`docker compose build` or the Makefile
    target) so the import resolves in-container.

## 2. Tavily search helper

2.1 In `concierge.py`, add a lazy accessor `_tavily_client()` that imports
    `TavilyClient` and constructs it from `os.environ.get("TAVILY_API_KEY")`
    at call time — returns `None` (or raises into the caller's except) when
    the key is unset. No module-level client, no import-time key read;
    importing `concierge.py` must stay credential-free.
2.2 Add `_tavily_search(query: str) -> str` — a **synchronous** helper that
    calls `client.search(query, search_depth="basic", include_answer=True,
    max_results=3)` and condenses the response for voice: prefer the
    `answer` field; fall back to joining the top results' `content` snippets;
    strip/skip URLs; cap the returned string at a speakable length
    (~600 chars). Returns a plain-sentence string.
2.3 Define the speakable fallback constant (e.g. `_DESTINATION_INFO_FALLBACK =
    "I couldn't look that up just now — ask me again in a moment."`).

## 3. Tool impl

3.1 Add `async def destination_info_impl(session_id: str, question: str) ->
    str`: resolve the pinned trip with `await ensure_trip_context(session_id)`
    (cache-first — no extra BigQuery read on later turns); if a trip is
    pinned, build the query as the question plus the trip's destination(s)
    and `start_date`–`end_date`; if unpinned, use the question verbatim.
3.2 Run the search off the event loop:
    `await asyncio.wait_for(asyncio.to_thread(_tavily_search, query),
    timeout=8)`.
3.3 Wrap the entire body in try/except returning
    `_DESTINATION_INFO_FALLBACK` on **any** failure — missing key, import
    error, Tavily API error, timeout, empty results. The tool never raises.

## 4. Registration & instructions

4.1 In `build_agent`, add the `_destination_info(question: str)` closure with
    a docstring the model routes on ("Live info about what's happening at
    the traveler's destination — events, things to do, local
    recommendations. Use when the traveler asks about the place they're
    going.") and register it:
    `function_tool(_destination_info, name_override="destination_info")` —
    always registered, no key check at build time.
4.2 Add one sentence to `BASE_INSTRUCTIONS`: when the traveler asks what's
    happening at their destination or for things to do, call
    `destination_info` and relay its answer conversationally — do not offer
    it unprompted, and never read URLs aloud.

## 5. Tests

All hermetic — mock at the Tavily-client boundary (monkeypatch
`_tavily_client` / `_tavily_search`); no `TAVILY_API_KEY`, no network.

5.1 `destination_info_impl` with a pinned trip: the query passed to the
    (mocked) search contains the question AND the trip's destination and
    dates.
5.2 Unpinned session: the query is the question verbatim; no error.
5.3 Condensing: a mocked Tavily response with an `answer` returns that
    answer; one without `answer` falls back to snippets; result is capped
    and URL-free.
5.4 Failure paths each return the speakable fallback and never raise:
    missing key, client exception, `asyncio.TimeoutError` (mock a slow
    search), empty results.
5.5 `build_agent` registers `destination_info` (tool present by name in the
    agent's tools), with no `TAVILY_API_KEY` in the environment.
5.6 Import hygiene: importing `concierge.py` without the key stays clean
    (implicitly covered by the whole bare suite — no dedicated test needed
    unless a laziness bug appears).

## 6. Deployment

6.1 Set the key on the service (one-time, survives redeploys):
    `gcloud run services update vocal-bridge-be-dev --region us-west1
    --update-env-vars TAVILY_API_KEY=…`
6.2 Land the branch on `vb/dev` by PR; CI builds, tests inside the image,
    and deploys. If the webhook is missed:
    `gcloud builds triggers run vocal-bridge-be-pr-to-dev --branch=vb/dev`.
6.3 Live spot-check per validation.md (web_call `/query` seam — no call
    quota spent).
