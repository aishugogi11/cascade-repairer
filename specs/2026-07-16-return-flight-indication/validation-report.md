# Validation Report — Phase 34: Return-flight indication
**Branch:** `vb/dev` · **Commit:** `c4fa49f031547905d752b65d7aab2e9dc935dc32` · **Date:** 2026-07-16

## Summary

**FAIL.** All automated criteria pass (`547 passed, 12 skipped, 11 deselected`), the feature is merged, CI is green, and Cloud Run serves the exact merge image. The deployed conversational contract does not pass: clean sessions sometimes skip the required return-date question, and every successful live answer tested omitted the required “I can't book the return from here” honesty framing. The core safety invariant does pass live: return results create no pending options and cannot be booked.

## Criterion-by-criterion results

### Automated

1. **Criterion:** Pinned trip plus date builds a reverse-route, human-dated Tavily query; a dateless call builds a route-only query.
   - **Status:** PASS
   - **Evidence:** `backend/tests/test_check_return_flights.py::test_pinned_trip_with_date_queries_reverse_route_and_query_date`, `::test_pinned_trip_dateless_queries_route_only`, and `::test_multi_destination_trip_uses_primary_destination`; implementation at `backend/api/concierge.py::check_return_flights_impl`.
   - **Notes:** The dated assertion is exactly `flights from LAX to JFK on July 26, 2026`; the dateless assertion is exactly `flights from LAX to JFK`.

2. **Criterion:** A successful tool result starts with the baked-in honesty framing and contains the mocked indication.
   - **Status:** PASS
   - **Evidence:** `test_pinned_trip_with_date_queries_reverse_route_and_query_date` asserts exact equality with `_RETURN_FRAMING + _INDICATION`.
   - **Notes:** This passes at the tool boundary. The spoken agent surface does not preserve the framing; see Manual 1–3 and Tone check.

3. **Criterion:** An unpinned session returns the no-trip line without searching.
   - **Status:** PASS
   - **Evidence:** `test_unpinned_session_gets_no_trip_line_without_searching` asserts `_NO_TRIP_SPOKEN` and an untouched mocked-search call list.
   - **Notes:** The deployed unpinned probe also returned “I don’t see a booked trip for you yet” without crashing.

4. **Criterion:** Missing route ends return a fallback without search or exception.
   - **Status:** PASS
   - **Evidence:** `test_trip_missing_route_ends_gets_fallback_without_searching`.
   - **Notes:** Both missing origin and missing destinations are exercised together.

5. **Criterion:** Search exception, timeout, and empty answer return an honest, route-aware fallback without invented airline, count, or time details.
   - **Status:** PASS
   - **Evidence:** `test_search_exception_returns_route_aware_fallback`, `test_timeout_returns_route_aware_fallback`, `test_missing_key_returns_route_aware_fallback`, and `test_empty_answer_returns_route_aware_fallback`.
   - **Notes:** The shared assertion rejects `Delta`, `American`, `JetBlue`, `nonstop`, and clock punctuation.

6. **Criterion:** Successful return checks leave flight options, latest-search state, booking writes, and the pinned context untouched.
   - **Status:** PASS
   - **Evidence:** `test_return_check_stores_nothing_bookable` snapshots `_SESSION_FLIGHT_OPTIONS`, `_LATEST_SEARCH`, and the pinned context, and asserts no BigQuery select or DML call.
   - **Notes:** The deployed follow-up “book option one” was refused; the status payload had no `pending_options`, and `latest_trip_id` remained `96770285-9072-4ed0-9dc6-c877c5d1def4`.

7. **Criterion:** `build_agent` always registers `check_return_flights`; instructions name the tool and require asking for a date first.
   - **Status:** PASS
   - **Evidence:** `test_tool_always_registered_without_key`, `test_instructions_route_return_questions_to_the_tool`, and `backend/tests/test_concierge.py::test_agent_uses_fast_model_and_exposes_guided_toolset`.
   - **Notes:** These are structural/string assertions. They do not prove that the live model follows the instruction consistently.

8. **Criterion:** The full bare suite passes without regressions.
   - **Status:** PASS
   - **Evidence:** `docker compose exec -T backend python -m pytest` → `547 passed, 12 skipped, 11 deselected, 7 warnings in 13.74s`. Targeted return/Concierge/destination tests: `71 passed, 1 warning in 4.99s`.
   - **Notes:** The default non-`cert` selection matches `backend/pytest.ini` and `validation.md`.

### Manual

1. **Criterion:** “is there a way to get home” asks for the return date, then produces a real-airline indication with the honesty framing and no speech artifacts.
   - **Status:** FAIL
   - **Evidence:** Against deployed image `c4fa49f`, a fresh pinned session answered immediately: “Yes — there are flights back from LAX to JFK on July 23.” It did not ask for a date. The follow-up “July 26, 2026” answered “Yes — there are direct flights back from LAX to JFK on July 26.”
   - **Notes:** Both answers omitted the required framing; neither named the expected real airlines.

2. **Criterion:** “flights to get me back” routes through the same date-first return flow.
   - **Status:** FAIL
   - **Evidence:** One fresh session correctly asked, “What return date should I check? If you want, I can use July 23 from your trip.” After “July 26, 2026,” it named JetBlue, American Airlines, and Delta Air Lines but began “Yes — there are direct return flights…”, omitting “I can't book the return from here.” A second fresh session skipped elicitation entirely and answered for July 23.
   - **Notes:** Tool routing occurs, but date elicitation is nondeterministic and the spoken framing is not preserved.

3. **Criterion:** Declining the date with “whenever works” produces a general, dateless route indication without stalling.
   - **Status:** FAIL
   - **Evidence:** The fresh session had already skipped date elicitation; after “whenever works,” it answered, “Yes — return flights from LAX to JFK do exist whenever works.”
   - **Notes:** The phrase was treated like a date instead of triggering a dateless lookup, and the spoken result is not conversationally valid.

4. **Criterion:** Return information never becomes bookable or creates a second trip.
   - **Status:** PASS
   - **Evidence:** Immediately after a real-airline return answer, “book option one” returned “I can’t book return flights from here…”. The trip status had no `pending_options`; `latest_trip_id` was unchanged.
   - **Notes:** This agrees with the stronger automated state-purity assertion.

5. **Criterion:** An unpinned return question gets the no-trip line, not a crash or a search about an unknown route.
   - **Status:** PASS
   - **Evidence:** A fresh unpinned `/v1/web_call/query` session returned “I don’t see a booked trip for you yet…” without error.
   - **Notes:** No-search behavior is proved hermetically by Automated 3.

6. **Criterion:** A return question during repair remains answerable without affecting repair or consent state.
   - **Status:** UNTESTABLE
   - **Evidence:** Not run against the shared deployed trip because creating the required disruption consumes outbound-call quota and mutates the active demo state.
   - **Notes:** `validation.md` labels this best-effort and excludes it from the required manual items 1–5.

### Tone check

- **Criterion:** Spoken output is short, conversational, sanitized, and explicitly framed as an indication rather than bookable inventory; fallback invents nothing.
- **Status:** FAIL
- **Evidence:** No tested successful live answer preserved “I can't book the return from here.” The dateless run produced the malformed sentence “return flights … do exist whenever works.” No URLs, Markdown, fare-class letters, or airline codes appeared.
- **Notes:** Sanitization passes; honesty framing and conversational reliability do not.

### Definition of done

1. **Criterion:** All automated assertions pass in the bare in-container suite.
   - **Status:** PASS
   - **Evidence:** `547 passed, 12 skipped, 11 deselected`.

2. **Criterion:** Manual walkthrough items 1–5 pass with evidence saved in the feature directory.
   - **Status:** FAIL
   - **Evidence:** This report records failures for Manual 1–3; Manual 4–5 pass.

3. **Criterion:** `DEMO_FLOW.md` and the README run sheet document the return beat.
   - **Status:** PASS
   - **Evidence:** `DEMO_FLOW.md` documents the Phase 34 return flow; README step 2b documents the optional return check and its non-bookable posture.

4. **Criterion:** The feature is merged to `vb/dev`, CI is green, and the merge is deployed.
   - **Status:** PASS
   - **Evidence:** PR #67 is merged into `vb/dev` at `c4fa49f`; Cloud Build `8fe97771-5dbc-4788-b60e-2d8ac273020c` is `SUCCESS`; Cloud Run revision `vocal-bridge-be-dev-00130-gvz` is ready and serves image tag `c4fa49f` at 100% traffic.

5. **Criterion:** Roadmap Phase 34 is marked complete.
   - **Status:** PASS
   - **Evidence:** `specs/roadmap.md` marks Phase 34 `[x] COMPLETE (implementation; manual QA pending)`.
   - **Notes:** The explicit “manual QA pending” qualifier remains accurate because this validation failed that QA.

## Missing tests

- Manual 1–3 have no automated coverage at the actual agent surface. Existing tests prove tool behavior and instruction text, but not that `/v1/web_call/query` elicits a date or preserves the tool's honesty framing. Proposed deployed smoke: `backend/tests/test_check_return_flights_live.py::test_return_conversation_preserves_date_and_framing_contract` — use a unique pinned session, assert the first turn asks for a date, then assert the final response retains the non-bookable framing and real indication. Keep it outside the hermetic default suite.
- Manual 6 lacks a zero-quota integrated test. Proposed hermetic test: `backend/tests/test_check_return_flights.py::test_return_check_during_active_repair_preserves_repair_state` — seed an active repair/session snapshot, call the return implementation, and assert repair events, consent state, and option state are byte-for-byte unchanged.
- No validator-written tests were added. A mocked tool-boundary test would duplicate passing coverage and would not reproduce the observed live-model failure.

## Gaps in validation.md

- What deterministic contract should ensure the model preserves the tool's honesty prefix: verbatim tool-result delivery, a stronger instruction assertion, or a non-LLM response path?
- How many clean deployed sessions must pass the date-elicitation flow before stochastic routing is considered validated?
- What zero-quota seam should validators use for Manual 6, or should that best-effort item remain explicitly non-blocking and reportable as untested?

## Risks not covered by validation.md

- The full suite emits six unawaited-coroutine warnings in Concierge/repair tests, plus one dependency deprecation warning. These do not fail Phase 34 criteria, but the coroutine warnings can hide async cleanup defects; roadmap Phase 24 already tracks this debt.
