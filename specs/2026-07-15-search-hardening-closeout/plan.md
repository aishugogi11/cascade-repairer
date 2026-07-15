# Plan — Search-hardening close-out (Phase 30)

Four independently-implementable task groups. Order is arbitrary except that
Group 5 (validation) runs last. Groups 1 and 4 are pure additions; Group 2 is a
small edit to production code with its own tests; Group 3 is a shell-script edit.

## 1. Behavior fix — clear stale options on non-optioned returns

Target: `backend/api/concierge.py`, `search_flights_impl` (line ~422).

1.1. Add a small local helper (or inline block) that clears both slots for the
     current session, mirroring `book_flight_impl`'s idiom exactly:
     ```python
     _SESSION_FLIGHT_OPTIONS.pop(session_id, None)
     global _LATEST_SEARCH
     if _LATEST_SEARCH is not None and _LATEST_SEARCH.session_id == session_id:
         _LATEST_SEARCH = None
     ```
     Prefer a nested helper `def _clear_search_state():` inside the function (it
     needs `global _LATEST_SEARCH`) or a module-level
     `_clear_session_search(session_id)` — pick whichever reads closest to the
     existing code; do not introduce a new clearing idiom.
1.2. Call it before **each** of the four non-optioned returns: missing-inputs
     (line ~434), unsupported-market (~445), search-error (~455), and
     no-options (~457). The two optioned returns are untouched — they store
     fresh options.
1.3. Do not change any of the four returned strings. Keep the comments terse.

## 2. Test — POST-path 401 token refresh

Target: `backend/tests/test_sabre_instaflights.py`.

2.1. Add `test_post_401_clears_token_and_retries_once(monkeypatch)`, patterned
     on `test_401_clears_token_refetches_and_retries_once` (line ~653) but
     driving `real._post(path, payload)` directly (or `flight_search` if a
     public entry reads cleaner — decision 4 prefers the direct `_post` call).
2.2. Handler: serve `/v2/auth/token` with incrementing tokens; on the first
     POST to the target path return `httpx.Response(401, …)`, on the second
     capture the `Authorization` header and return a `200`. Assert: two token
     mints, two sends, the retry carried the **fresh** bearer, and `real._token`
     is the fresh token.
2.3. Add `test_post_persistent_401_raises_after_one_retry(monkeypatch)`,
     patterned on `test_persistent_401_raises_after_exactly_one_retry` (~686):
     every POST returns 401, assert `_post` raises `httpx.HTTPStatusError` after
     exactly one retry (two sends).
2.4. Reuse `_mock_transport` and `_configured_real_client`. Use `_DAY` /
     computed dates if the payload needs a date — no literal travel dates.

## 3. Test — six-case metro aliases

Target: `backend/tests/test_sabre_instaflights.py`.

3.1. Add `test_all_metro_aliases_apply_as_origin_and_destination`, parametrized
     with `@pytest.mark.parametrize` over the three `(metro, airport)` pairs
     `("NYC","JFK")`, `("WAS","IAD")`, `("CHI","ORD")` **and** both positions
     (origin vs destination) — 6 cases total (e.g. parametrize over a list of
     6 `(origin_in, dest_in, expect_origin, expect_dest)` tuples, or the cross
     product).
3.2. For each case: stub `supported_markets` to return the **airport** pair only
     (metro absent, like the real list — pattern from the existing single-case
     test at ~870), capture the client request via a stubbed
     `instaflights_search`, run `search_flights_impl`, and assert both (a) the
     captured request carries the airport codes (aliased), and (b) the result is
     not `_UNSUPPORTED_MARKET_LINE` (the aliased pair reached and passed the
     market check). The non-aliased position in each case uses a plain
     supported airport (e.g. `SFO`).
3.3. Keep the existing single-case and pass-through tests; this is additive.

## 4. Tooling — pin `git_pull_dev.sh` base branch

Target: `git_pull_dev.sh` (repo root), resolution block (lines ~17–33).

4.1. Update the comment block (lines 17–20) to document the new order:
     `1. BASE_BRANCH env override → 2. vb/dev (this repo's integration branch)
     → 3. gh default branch → 4. git origin/HEAD`.
4.2. Insert a `vb/dev` step immediately after the `BASE_BRANCH` env check and
     before the `gh`/`origin/HEAD` fallbacks — set `BASE_BRANCH="vb/dev"` as the
     default (guarded so an explicit env override still wins). Keep the
     `gh`/`origin/HEAD` branches as later fallbacks so the script still works if
     the integration branch is ever renamed.
4.3. Leave `MERGE_EXTRA="--admin"` and the rest of the script unchanged — only
     the base-branch resolution is in scope.

## 5. Validation

5.1. Run the full bare-container suite; confirm the new tests pass and no new
     warnings appear beyond the allowed baseline (1 Starlette deprecation + 6
     pre-existing unawaited-coroutine warnings).
5.2. Add a targeted behavior check for item 3: after an optioned search stores
     options, a follow-up empty/error/unsupported search clears them (a repeat
     `book_flight_impl` then finds nothing to book). Cover this as a test or a
     documented ephemeral walkthrough.
5.3. Deliberate cert run (`pytest -m cert`) on implementation day if credentials
     are available — read-only subset is sufficient; capture dated output.
5.4. Paste cert-run and walkthrough transcripts into the PR description
     **before merge** (Definition of Done B — the Phase 28 process lesson).
5.5. Mark Phase 30 `[x] COMPLETE` in `specs/roadmap.md`.
