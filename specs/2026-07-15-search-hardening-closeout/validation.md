# Validation — Search-hardening close-out (Phase 30)

## Automated

Run the full bare-container suite (the exact artifact CI runs):

```
docker compose build backend
docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -q
```

**Assertions that must exist and pass in the bare-container run:**

1. **Suite green.** All tests pass; skips/deselects are the existing cert
   deselects. No new warnings beyond the allowed baseline — one Starlette
   deprecation and the six pre-existing unawaited-coroutine `RuntimeWarning`s
   (the Phase 24 async-hygiene debt, out of scope here).
2. **Six-case metro aliases (criterion 6, literal reading).**
   `test_all_metro_aliases_apply_as_origin_and_destination` exists and passes
   with **all six** cases: `NYC→JFK`, `WAS→IAD`, `CHI→ORD`, each asserted in
   **both** the origin and destination position. Each case asserts the captured
   client request carries the airport code (not the metro code) **and** that the
   result is not `_UNSUPPORTED_MARKET_LINE` (reached and passed the market
   check). Source inspection alone does **not** satisfy this — the assertions
   must be committed.
3. **POST-path 401 refresh (criterion 5 note).**
   `test_post_401_clears_token_and_retries_once` proves `_post` sends the retry
   with a freshly minted bearer after one 401 (two token mints, two sends, retry
   used the fresh token). `test_post_persistent_401_raises_after_one_retry`
   proves a second 401 raises `httpx.HTTPStatusError` after exactly one retry.
   Both drive the POST path (not GET).
4. **Stale options cleared (behavior fix).** A test proves that after an
   optioned search stores options for a session, a subsequent **empty**,
   **error**, and **unsupported-market** search each clears both
   `_SESSION_FLIGHT_OPTIONS[session_id]` and the session's `_LATEST_SEARCH`, so
   a following `book_flight_impl("option one")` finds nothing to book (returns
   its no-options speakable string). A never-searched or other-session slot is
   never wiped (ownership guard holds).
5. **Computed dates only.** No literal travel date appears in any test or
   fixture added by this phase (`_DAY` / `date.today()` + `timedelta`).

## Manual

6. **Behavior walkthrough — stale options.** In an ephemeral container (mock
   mode), search a valid pair (options stored), then search an all-unmappable or
   no-results pair; confirm the agent speaks the no-flights line **and** a
   follow-up "book option one" no longer books the earlier flight. Capture the
   two agent turns.
7. **`git_pull_dev.sh` resolution.** Confirm that with no `BASE_BRANCH` env set,
   the script resolves the base branch to `vb/dev` (echo line `==> Base branch:
   vb/dev`), and that `BASE_BRANCH=main ./git_pull_dev.sh` still overrides to
   `main`. Verify by dry inspection / `--help`-style dry run without actually
   merging.
8. **Deliberate cert run (if credentials available on implementation day).** Run
   `pytest -m cert` (read-only subset sufficient — auth, supported markets, real
   priced search, timezone parity); capture dated output. The PNR-mutating
   tripwires may be skipped by an independent validator.

## Tone check

9. No user-facing copy changed. Confirm the four non-optioned return strings in
   `search_flights_impl` are byte-identical to before, and no new jargon leaked
   into any reply.

## Definition of done

- **A.** Every automated assertion in §1–5 exists and passes in the
  bare-container run.
- **B.** The cert run (§8) and the reachable walkthroughs (§6–7) are evidenced
  in the PR description with **transcript/output snippets pasted before merge** —
  not prose claims, not "see comments." (Direct remediation of the Phase 28
  DoD-B FAIL.)
- **C.** The stale-options fix clears on **all four** non-optioned returns
  (missing-inputs, unsupported-market, error, no-options), not just the
  honest-empty path.
- **D.** `git_pull_dev.sh` defaults to `vb/dev` with the env override preserved,
  and the comment block documents the new resolution order.
- **E.** Phase 30 is marked `[x] COMPLETE` in `specs/roadmap.md`.
