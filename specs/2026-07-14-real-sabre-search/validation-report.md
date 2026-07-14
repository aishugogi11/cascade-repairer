# Validation Report — Real Sabre Search in the Demo Path

**Branch:** `vb/feature/real-sabre-search`  
**Commit:** `0e42cd5f03870c3e3b06fda914c8c0dd03d9b4bc`  
**Date:** 2026-07-14

## Summary

**FAIL.** The hermetic suite is green and the independent credentialed InstaFlights check passes, but two required behaviors fail: the parser does not reject an unmapped intermediate connection airport, and mock-mode west-to-east flights can arrive before they depart because fixed Pacific-fiction times are reinterpreted as airport-local. The merged PR also has an empty description, so the required real-mode walkthrough, screenshot/transcript, and Cloud Run flip-recipe evidence are absent.

## Criterion-by-criterion results

### Automated

1. **Criterion:** Suite green, hermetically.
   - **Status:** PASS
   - **Evidence:** `docker compose exec -T backend pytest` collected 378 tests, deselected 8 `cert` tests, and finished with `358 passed, 12 skipped, 8 deselected, 7 warnings in 6.06s`. `backend/tests/test_sabre_instaflights.py` contributed 23 passing tests.
   - **Notes:** The seven warnings do not fail this criterion; six are pre-existing unawaited-coroutine warnings already tracked by roadmap Phase 24, and one is a Starlette deprecation warning.

2. **Criterion:** `onlineitinerariesonly=N` is unconditional.
   - **Status:** PASS
   - **Evidence:** `backend/api/sabre/real_client.py:88-97` overwrites the serialized request value with `N`. `backend/tests/test_sabre_instaflights.py::test_real_client_always_sends_onlineitinerariesonly_n` passes after deliberately constructing a request with `Y`.
   - **Notes:** The test also verifies the GET request carries origin, destination, and bearer authentication.

3. **Criterion:** Pacific conversion is real conversion, with computed test dates.
   - **Status:** PASS
   - **Evidence:** `backend/api/concierge.py:361-368` localizes the endpoint wall clocks in their airport zones before conversion to `America/Los_Angeles`. `test_parser_converts_airport_local_to_pacific` proves JFK `07:20` becomes `04:20` PT. Phase 27 fixtures derive `_DAY` from `date.today() + timedelta(...)`; no literal travel date was added in the feature's test diff.
   - **Notes:** Existing unrelated tests elsewhere in `backend/tests/` still contain literal dates; see “Gaps in validation.md” for the scope ambiguity.

4. **Criterion:** Red-eye day shift produces a distinct arrival date and `end_ts > start_ts`.
   - **Status:** PASS
   - **Evidence:** `test_parser_red_eye_shifts_the_pt_arrival_date` and `test_red_eye_booking_writes_end_ts_after_start_ts` pass. `backend/api/concierge.py:478-490` builds `end_ts` from `FlightOption.arrive_date`.
   - **Notes:** None.

5. **Criterion:** An itinerary touching an unmapped airport is skipped; the next itinerary takes its slot; all-unmappable returns the existing no-flights line.
   - **Status:** FAIL
   - **Evidence:** `backend/api/concierge.py:350-360` checks only `segments[0].DepartureAirport` and `segments[-1].ArrivalAirport`. A mapped `JFK → XXQ → LAX` itinerary is therefore retained even when `XXQ` is absent from the timezone table. The existing `test_parser_skips_unmapped_airport_in_favor_of_the_next` (`backend/tests/test_sabre_instaflights.py:176-185`) covers only an unmapped endpoint, not an unmapped connection. The all-unmappable endpoint case is covered by `test_parser_all_unmappable_yields_no_options` and `test_all_unmappable_search_speaks_the_no_flights_line`.
   - **Notes:** Requirements decision 2 says each segment time is localized and an unknown airport skips the itinerary, so this is a behavior defect rather than merely a missing assertion.

6. **Criterion:** Silent per-call fallback in real mode; mock mode never constructs a real request.
   - **Status:** PASS
   - **Evidence:** `backend/api/sabre/client.py:31-41` logs the operation and dispatches that call to the mock after any real-client exception. `test_dispatcher_real_failure_falls_back_to_mock_and_logs`, `test_search_flights_real_mode_failure_serves_mock_silently`, and `test_dispatcher_mock_mode_never_touches_the_real_client` all pass.
   - **Notes:** The end-to-end fallback test also asserts the spoken reply omits failure, sandbox, and mock terminology.

7. **Criterion:** Unsupported markets fail speakably without searching; a `None` market map proceeds.
   - **Status:** PASS
   - **Evidence:** `backend/api/concierge.py:417-425`; passing tests `test_unsupported_market_redirects_and_never_searches` and `test_markets_none_skips_validation_and_searches`.
   - **Notes:** The redirect proposes the known-good San Francisco-to-New York route.

8. **Criterion:** Speakable options remain limited to three, use word-number labels, rounded prices, 12-hour times, and no codes.
   - **Status:** PASS
   - **Evidence:** `backend/api/concierge.py:295-330,347-394` enforces the three-option limit and constructs the spoken-only fields. `test_parser_spoken_contract_no_codes_rounded_prices` and `test_search_flights_end_to_end_on_the_mock` pass.
   - **Notes:** Structured airline/currency fields remain available for booking but are not interpolated into `spoken`.

9. **Criterion:** `pending_options` shape is unchanged.
   - **Status:** PASS
   - **Evidence:** `backend/api/concierge.py:587-601`; `test_pending_options_payload_is_the_phase_21_contract` asserts the outer keys and exact seven option keys.
   - **Notes:** The additive `arrive_date` remains internal and does not leak into the Phase 21 response contract.

10. **Criterion:** Diff scope preserves BFM shapes and repair searches and contains no raw credential/token material.
    - **Status:** PASS
    - **Evidence:** `git diff --numstat vb/dev -- backend/api/sabre/shapes.py` reports `93 0` (additive-only); the additions begin after the pre-existing Booking Management/BFM models. `backend/api/repair_tools.py` has no feature diff and still calls `sabre_client.flight_search` at lines 111 and 187. The raw `SABRE_API_USER_ID` and `SABRE_API_SECRET` currently used for CERT are absent from the complete branch diff; token-like added lines contain only the explicit fake fixture `T1RLtoken` or the `Bearer {token}` template. `git diff --check vb/dev...HEAD` is clean.
    - **Notes:** The plan file was mechanically scanned for credential/token material without reading its content, preserving the validator's plan-blindness requirement.

### Manual

11. **Criterion:** Credentialed live InstaFlights check returns at least one real priced itinerary for a supported pair on a computed future date.
    - **Status:** PASS
    - **Evidence:** `python -m pytest -m cert tests/test_sabre_cert.py::test_instaflights_search_returns_real_priced_itineraries -q`, run in the backend container with the documented credential passthrough, completed `1 passed in 2.25s` on 2026-07-14.
    - **Notes:** The test performs only authenticated GETs and emitted no credential/token material.

12. **Criterion:** Real-mode `/v1/web_call/query` search → book → complete walkthrough, including matching booking-page options and mock booking rows.
    - **Status:** UNTESTABLE
    - **Evidence:** PR #43 (`real flights`) is merged, but `gh pr view` reports an empty body; there is no transcript snippet, booking-page screenshot/equivalent, or row/poll evidence. The validator did not create external BigQuery booking rows to substitute for the missing implementation artifact.
    - **Notes:** The hermetic tests prove the component contracts, not the required live endpoint/UI walkthrough.

13. **Criterion:** Voice edge cases cover unsupported route, garbled city, and mid-conversation network/config failure.
    - **Status:** UNTESTABLE
    - **Evidence:** Unsupported-route and failing-client behavior pass at the tool-function seam, but no voice transcript or `/v1/web_call/query` artifact exists for the garbled-city and mid-conversation cases.
    - **Notes:** Model-dependent extraction of a garbled city cannot be inferred from the blank-argument unit test.

14. **Criterion:** Full guided-booking walkthrough is unchanged with `SABRE_MODE` unset.
    - **Status:** FAIL
    - **Evidence:** A focused mock-mode run of `search_flights_impl("validator-mock", "SFO", "JFK", computed_future_date)` spoke: `Option one: nonstop, leaves at 8 AM and lands at 7:05 AM`. Its structured values were `depart=2026-08-04T08:00` and `arrive=2026-08-04T07:05`. `backend/api/sabre/mock_client.py:128-165` emits the old Pacific-fiction wall clocks as offset-less airport-local values, and the parser then timezone-converts them. Before Phase 27, the mock path spoke the fixed clocks directly (`8 AM` → `10:05 AM`).
    - **Notes:** The first offered option can therefore produce `end_ts < start_ts` when booked. Existing mock coverage uses MSP→SFO and does not assert the times, so the regression stays green.

### Tone check

15. **Criterion:** New user-facing copy is short, warm, speakable, and free of technical/code jargon.
    - **Status:** PASS
    - **Evidence:** `backend/api/concierge.py:299-310,322-331,430-453`. The unsupported-market line uses the allowed “demo system” phrasing; option copy uses word labels, 12-hour times, and “about … dollars.” The spoken-contract tests pass.
    - **Notes:** None.

### Definition of done

16. **Criterion:** All automated assertions exist and pass in the bare container run.
    - **Status:** FAIL
    - **Evidence:** The bare run is green, but no assertion covers an unmapped intermediate connection airport or west-to-east mock clock ordering, and both required behaviors fail (criteria 5 and 14).
    - **Notes:** A green suite is insufficient when the specified case is absent from the suite.

17. **Criterion:** Credentialed live check and real-mode walkthrough succeeded on implementation day and are evidenced in the PR description.
    - **Status:** FAIL
    - **Evidence:** The independent live search check passes, but PR #43's body is empty and no walkthrough/screenshot/transcript evidence exists there.
    - **Notes:** The validator's later live GET cannot establish that the full implementation-day walkthrough occurred.

18. **Criterion:** Mock-mode regression walkthrough is clean.
    - **Status:** FAIL
    - **Evidence:** The validator's focused mock SFO→JFK search produced two options whose spoken and structured arrival times precede their same-day departure times. No clean implementation-day walkthrough artifact exists in PR #43.
    - **Notes:** This is a deterministic regression, not merely missing evidence.

19. **Criterion:** Roadmap Phase 27 is marked complete.
    - **Status:** PASS
    - **Evidence:** `specs/roadmap.md:13` is marked `[x] COMPLETE (implementation; manual QA pending)`.
    - **Notes:** The “manual QA pending” qualifier agrees with the missing walkthrough evidence.

20. **Criterion:** Cloud Run flip recipe is referenced, not executed, in the PR description.
    - **Status:** FAIL
    - **Evidence:** PR #43's description is empty.
    - **Notes:** The recipe exists elsewhere in project documentation, but the criterion explicitly requires the PR description.

## Missing tests

- `backend/tests/test_sabre_instaflights.py::test_parser_skips_itinerary_with_unmapped_connection_airport` — build a first itinerary with mapped origin/final destination and an unmapped connection airport, followed by a fully mapped itinerary; assert the first is absent and the second is renumbered into its slot.
- `backend/tests/test_sabre_instaflights.py::test_mock_west_to_east_preserves_pacific_wall_clock_order` — search SFO→JFK in mock mode and assert each option's arrival instant follows departure and the established first-option copy remains `8 AM` → `10:05 AM`.
- `backend/tests/test_web_call.py::test_real_search_book_complete_contract` — hermetically drive the `/v1/web_call/query` seam with a captured InstaFlights response and repository fakes; assert spoken options match `pending_options`, booking clears the slot, `raw_response.source == "voice_guided_booking"`, and completion preserves the trip.
- `backend/tests/test_concierge.py::test_mock_guided_booking_full_regression` — run search → choose option → complete against deterministic mock search and fake repositories in one scenario, asserting three options and all expected writes.
- The voice-level garbled-city criterion has no deterministic test contract. A fixture should name the exact utterance/tool arguments before an automated test is feasible.

No validator-authored test file was added; the missing intermediate-airport case is evidenced directly by the parser's endpoint-only checks.

## Gaps in validation.md

- Does “computed dates only, no literal travel dates anywhere in tests or fixtures” apply only to Phase 27 additions, or to the entire pre-existing test tree, which contains many fixed dates?
- Can an independent validator's rerun replace missing PR-description evidence, or must an empty PR description remain a hard definition-of-done failure?
- What exact artifact qualifies as “equivalent” to the booking-page screenshot, and where must it be stored after a PR has merged?
- Which concrete garbled-city utterances and expected tool arguments define that voice edge case independently of model variability?

## Risks not covered by validation.md

- `RealSabreClient._get_token` says it refetches on HTTP 401, but `_get` and `_post` call `raise_for_status()` without clearing/retrying the cached token (`backend/api/sabre/real_client.py:44-86`). After token expiry, real-mode searches can silently mock-fallback until the process restarts.
- The static timezone table has no parity check against all airport codes returned by the live supported-markets endpoint, so supported routes may be honestly but unexpectedly skipped.
- The bare suite still emits six unawaited-coroutine warnings in concierge/repair tests; roadmap Phase 24 already tracks that debt.
- Validation ran with a pre-existing uncommitted `README.md` change. No production/test file differed from the recorded commit during validation.
