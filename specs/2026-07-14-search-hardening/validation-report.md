# Validation Report — Search Hardening (Phase 28)

**Branch:** `vb/dev` (post-merge; tree matches feature tip `171546c`)

**Commit:** `f55906d99ed3bb1b998ed7a4352baa6c8466a073`

**Date:** 2026-07-14

## Summary

**FAIL.** The implemented search behavior passed the hermetic suite, read-only CERT checks,
and independent mock/real walkthroughs. The acceptance package is incomplete: criterion 6
requires automated coverage for `NYC`, `WAS`, and `CHI` as origin or destination, but the
committed test covers only `NYC` as origin and `WAS` as destination; and the Definition of
Done requires transcript/output evidence for manual items 10–12 in the PR description, while
PR #45 contains only prose claims for those checks and points to comments that do not exist.

## Criterion-by-criterion results

### 1. Suite green

- **Criterion:** Full bare-container suite passes with no phase-introduced warnings.
- **Status:** PASS
- **Evidence:** `docker compose build backend` succeeded. The rebuilt-image run
  `docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -q` returned
  `375 passed, 12 skipped, 9 deselected, 7 warnings in 7.33s`.
- **Notes:** The warnings are the allowed baseline: one Starlette deprecation and the six
  pre-existing unawaited-coroutine warnings named in `validation.md`.

### 2. Unmapped connection skips the itinerary

- **Criterion:** Skip any itinerary touching an unmapped connection, preserve mapped
  multi-segment itineraries, renumber contiguously, and retain the all-unmappable no-flights
  behavior.
- **Status:** PASS
- **Evidence:** The bare suite passed
  `test_parser_skips_itinerary_with_unmapped_connection_airport`,
  `test_parser_mapped_multi_segment_still_parses`, and
  `test_all_unmappable_search_speaks_the_no_flights_line` in
  `backend/tests/test_sabre_instaflights.py`. The implementation checks both ends of every
  segment at `backend/api/concierge.py:370`.
- **Notes:** None.

### 3. Mock west-to-east ordering

- **Criterion:** Mock SFO→JFK options and booking timestamps remain chronologically ordered,
  option one speaks the classic 8 AM / 10:05 AM spread, and the reverse direction preserves
  that PT spread.
- **Status:** PASS
- **Evidence:** The bare suite passed
  `test_mock_west_to_east_preserves_pacific_wall_clock_order`,
  `test_mock_east_to_west_parses_to_the_same_pt_spread`, and
  `test_mock_west_to_east_booking_write_keeps_end_after_start`. An independent ephemeral
  container walkthrough on computed date `2026-08-04` observed all three arrivals after
  departure, option one saying “leaves at 8 AM and lands at 10:05 AM,” and a captured booking
  row with `2026-08-04T08:00:00-07:00 < 2026-08-04T10:05:00-07:00`.
- **Notes:** The walkthrough replaced repository writes with in-process captures; it made no
  external data changes.

### 4. Honest empty, strict

- **Criterion:** Treat only the documented InstaFlights no-results 404 as an honest empty;
  speak the no-flights line without mock fallback or stored options; preserve fallback for
  other 404s.
- **Status:** PASS
- **Evidence:** The bare suite passed
  `test_real_client_documented_404_returns_empty_response`,
  `test_real_client_404_message_fallback_without_error_code`,
  `test_real_client_other_404_still_raises`,
  `test_documented_empty_speaks_no_flights_end_to_end`, and
  `test_other_404_still_mock_swaps_at_the_dispatcher`. A live read-only CERT check for
  SFO→JFK on computed date `2026-07-16` returned “I couldn't find any flights for that day,”
  stored zero options, and emitted no fallback warning.
- **Notes:** Repeat-search stale state is a separate uncovered risk below.

### 5. Token refresh once

- **Criterion:** A 401 clears the cached token, obtains a new token, retries exactly once,
  succeeds when the retry succeeds, and raises after a persistent 401.
- **Status:** PASS
- **Evidence:** The bare suite passed `test_401_clears_token_refetches_and_retries_once` and
  `test_persistent_401_raises_after_exactly_one_retry`. Both `_get` and `_post` delegate to
  `_send_with_refresh` at `backend/api/sabre/real_client.py:86`.
- **Notes:** The committed tests exercise the GET path only; direct POST coverage is proposed
  under Missing tests.

### 6. Metro aliases

- **Criterion:** `NYC`/`WAS`/`CHI`, as origin or destination, reach both market validation
  and the client as `JFK`/`IAD`/`ORD`; unaliased codes remain unchanged.
- **Status:** FAIL
- **Evidence:** The implementation defines all three mappings and applies the same lookup to
  both request positions at `backend/api/concierge.py:306` and
  `backend/api/concierge.py:431`. An independent six-case runtime assertion passed for every
  alias in both positions (`ALIASES_OK 6/6 origin/destination cases`). However, the committed
  suite's `test_metro_codes_alias_to_airports_before_the_market_check` asserts only `NYC` as
  origin and `WAS` as destination; `CHI` and the other position combinations are absent.
- **Notes:** Because this criterion is explicitly under “Automated,” source inspection and an
  ephemeral validator command do not satisfy the requirement that all assertions exist in the
  bare-container test suite.

### 7. Dedupe

- **Criterion:** Duplicate itineraries collapse to two distinct, contiguously numbered
  options with no duplicate spoken clause.
- **Status:** PASS
- **Evidence:** `test_parser_dedupes_identical_itineraries` passed in the bare suite. The
  first-occurrence key and pre-numbering skip are at `backend/api/concierge.py:379`.
- **Notes:** None.

### 8. Computed dates

- **Criterion:** No literal travel date appears in this phase's added or modified tests and
  fixtures.
- **Status:** PASS
- **Evidence:** The test diff derives `_DAY` and `_NEXT_DAY` from `date.today()` and
  `timedelta`. Searching added test lines for ISO dates found only the historical prose
  “probed 2026-07-14,” not a travel-date fixture.
- **Notes:** This assessment uses the scope note in `validation.md`: only this phase's test
  and fixture diff is in scope.

### 9. Deliberate cert run

- **Criterion:** The credentialed cert suite passes on implementation day, including the new
  timezone-parity test, with dated output captured.
- **Status:** PASS
- **Evidence:** PR #45 records a dated `2026-07-14 19:41 CDT` transcript with all nine cert
  tests passing in `5.86s`. The validator independently reran the four read-only cases:
  auth, supported markets, real priced search, and timezone parity; all four passed in
  `3.48s`.
- **Notes:** The validator did not rerun the PNR-related booking/cancel tripwires because they
  can mutate external CERT state; the implementation-day PR transcript is the evidence for
  those cases.

### 10. Mock-mode walkthrough

- **Criterion:** On a computed future date, SFO→JFK speaks the classic ordered spread and
  booking option one produces sane timestamps.
- **Status:** PASS
- **Evidence:** Independent ephemeral-container observation on `2026-08-04`: three spoken
  options used the classic 8 AM / 11:30 AM / 6:15 AM departures; every arrival followed its
  departure; captured option-one booking timestamps were ordered from 08:00 to 10:05 PT.
- **Notes:** The behavior passes, but the required pre-merge PR transcript is missing; see
  Definition of Done B.

### 11. Real-mode honest-empty spot check

- **Criterion:** A live supported pair/date without cached content speaks the no-flights line
  and logs no mock fallback.
- **Status:** PASS
- **Evidence:** Read-only CERT observation on `2026-07-14` for SFO→JFK departing computed
  `2026-07-16`: no-flights line, zero stored options, no warning output.
- **Notes:** The behavior passes, but the required pre-merge PR transcript is missing; see
  Definition of Done B.

### 12. Real-mode happy path unchanged

- **Criterion:** A supported near-term pair still returns real, deduplicated spoken options
  without a metro redirect or duplicated clause.
- **Status:** PASS
- **Evidence:** Read-only CERT observation on `2026-07-14` for SFO→MIA departing computed
  `2026-07-16`: three distinct spoken options returned, three options were stored, and no
  fallback warning or metro redirect appeared.
- **Notes:** The behavior passes, but the required pre-merge PR transcript is missing; see
  Definition of Done B.

### 13. Tone check

- **Criterion:** No new user-facing jargon; any touched copy stays warm and speakable; the
  metro-code instruction stays terse and does not leak into replies.
- **Status:** PASS
- **Evidence:** The source diff changes only `BASE_INSTRUCTIONS` copy, adding “always a
  specific airport, never a metro or city code (New York is JFK, not NYC).” The bare suite
  passed `test_instructions_carry_the_airport_code_clause` and
  `test_parser_spoken_contract_no_codes_rounded_prices`; both independent live replies were
  short and contained no API/mock/sandbox jargon.
- **Notes:** None.

### Definition of Done A — automated assertions exist and pass

- **Criterion:** Every automated assertion above exists and passes in the bare-container run.
- **Status:** FAIL
- **Evidence:** The suite passes, but criterion 6 lacks committed assertions for `CHI` and
  for each alias in both request positions.
- **Notes:** See Missing tests.

### Definition of Done B — implementation-day PR evidence

- **Criterion:** The cert run and reachable walkthroughs are evidenced in the PR description
  with transcript/output snippets, not prose claims.
- **Status:** FAIL
- **Evidence:** PR #45 contains the cert transcript and a raw live no-results response, but
  its “Manual checks” section only says the mock walkthrough was covered/spot-checked and
  directs the real checks to “PR comments / conversation.” `gh pr view 45 --json comments`
  returned an empty comments list. There is no agent-output transcript for item 10, no
  no-fallback observation for item 11, and no real happy-path output for item 12.
- **Notes:** Validator observations after merge do not retroactively satisfy the PR-evidence
  requirement as written.

### Definition of Done C — timezone table updated

- **Criterion:** Any codes surfaced by parity validation are added to `AIRPORT_TZ`.
- **Status:** PASS
- **Evidence:** PR #45 says the first parity run surfaced 29 codes and lists their addition.
  The validator's live read-only parity rerun passed.
- **Notes:** None.

### Definition of Done D — roadmap complete

- **Criterion:** Phase 28 is marked `[x] COMPLETE` in `specs/roadmap.md`.
- **Status:** PASS
- **Evidence:** `specs/roadmap.md` marks Phase 28 `[x] COMPLETE (implementation; manual QA
  pending)`.
- **Notes:** None.

## Missing tests

- **Criterion 6:** Add
  `backend/tests/test_sabre_instaflights.py::test_all_metro_aliases_apply_as_origin_and_destination`,
  parametrized over `NYC→JFK`, `WAS→IAD`, and `CHI→ORD` in both request positions. Assert
  the normalized pair reaches both market validation and the captured client request.
- **Criterion 5:** Add
  `backend/tests/test_sabre_instaflights.py::test_post_401_clears_token_and_retries_once`.
  Use the mocked HTTP transport to assert `_post` sends the retry with a newly minted bearer
  token and raises after a second 401. The current tests cover the shared helper through GET
  only.

No validator test file was added; this report is the validator's only write.

## Gaps in validation.md

- Should criterion 6 require six committed assertions (all three aliases in both positions),
  or is one representative pair plus source inspection sufficient? This report applies the
  literal six-case reading.
- Can a post-merge validator transcript satisfy the PR-evidence Definition of Done, or must
  the transcript be present before merge in the PR description? This report applies the
  latter reading.
- Should independent validators rerun the PNR-related cert tripwires, which can mutate Sabre
  CERT state, or is a dated implementation transcript plus a fresh read-only subset the
  intended safety boundary?
- Is validation on post-merge `vb/dev` acceptable when the file names
  `vb/feature/search-hardening`? The validated tree is identical to feature tip `171546c`,
  but the validation could no longer gate the merge.

## Risks not covered by validation.md

- **Stale choice after an empty repeat search:** `search_flights_impl` returns from the
  no-options branch before clearing `_SESSION_FLIGHT_OPTIONS` or `_LATEST_SEARCH`. A validator
  probe observed three prior options still stored after a later empty result, leaving stale
  choices bookable.
- **Unrelated branch-automation change:** this feature rewrites `git_pull_dev.sh` to stage all
  changes, push, and merge with `--admin`. Its default base comes from `origin/HEAD`, which is
  `origin/main` in this checkout, while the repository's required integration branch is
  `vb/dev`.
