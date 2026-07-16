# Validation Report — Phase 35: Tavily destination-info tool

**Branch:** `vb/dev`  
**Commit:** `3099a6cbcdbb2ca845fd3e86904d90232e1bc072`  
**Date:** 2026-07-16

## Summary

**FAIL.** The shipping image builds, the hermetic suite is green, the deployed revision has the key, and the live unpinned, trip-aware, fallback, latency, and no-write checks pass. The acceptance contract still fails in two places: the result sanitizer returns bare `www.` URLs and Markdown unchanged, violating Automated 3 and the tone check; and Phase 35 remains in the roadmap instead of being archived through the required changelog close-out. No production code or existing test was modified during validation.

## Criterion-by-criterion results

### Automated 1 — Bare suite green, hermetic, zero new warnings

- **Criterion:** Run the bare suite in the shipping container with no `TAVILY_API_KEY`; it must stay green with no new warnings.
- **Status:** PASS
- **Evidence:** `docker compose exec -T -e TAVILY_API_KEY= backend pytest` collected 555 tests and finished `532 passed, 12 skipped, 11 deselected, 7 warnings in 16.64s`. `test_destination_info.py` passed all 13 tests and emitted no warning. [live-qa-2026-07-16.md](live-qa-2026-07-16.md) records that the seven-warning count is identical to the pre-change baseline.
- **Notes:** The output contains one existing Starlette deprecation and six existing unawaited-coroutine warnings; these are not new Phase 35 warnings.

### Automated 2 — Trip-aware query

- **Criterion:** A pinned query includes the question, destination(s), and dates; an unpinned query passes the question through unchanged.
- **Status:** PASS
- **Evidence:** `backend/tests/test_destination_info.py::test_pinned_trip_garnishes_query_with_destination_and_dates` and `::test_unpinned_session_searches_question_verbatim` passed. The implementation appends cached trip context at `backend/api/concierge.py:823`–`842`.
- **Notes:** The unpinned path performs no repository read because `ensure_trip_context` returns the no-trip result without a `trip_id`.

### Automated 3 — Speakable condensing

- **Criterion:** Prefer `answer`, fall back to snippets, cap length, and return no URLs.
- **Status:** FAIL
- **Evidence:** The answer/snippet and 600-character-cap tests pass, but an independent shipping-container probe supplied `Try **CicLAvia** at www.example.com/events.` as the mocked Tavily `answer`; `_tavily_search` returned that string unchanged. `_URL_RE` at `backend/api/concierge.py:780` matches only `http://` and `https://`. The existing `test_search_strips_urls_and_caps_length` covers only an `https://` URL.
- **Notes:** Bare `www.` URLs violate this criterion; the retained `**...**` also violates the tone check below. Live samples happened to be clean, but the implementation does not enforce the contract.

### Automated 4 — Never raises

- **Criterion:** Missing key, client error, timeout, and empty results return the speakable fallback.
- **Status:** PASS
- **Evidence:** `test_missing_key_returns_speakable_fallback`, `test_client_exception_returns_speakable_fallback`, `test_timeout_returns_speakable_fallback`, and `test_empty_results_return_speakable_fallback` passed. An independent no-key call returned `I couldn't look that up just now — ask me again in a moment.` in 0.164s.
- **Notes:** The expected fallback logs a warning with traceback but does not escape the tool.

### Automated 5 — Registration

- **Criterion:** `build_agent` always registers a tool named `destination_info`, even without the key.
- **Status:** PASS
- **Evidence:** `test_tool_always_registered_without_key` and `backend/tests/test_concierge.py::test_agent_uses_fast_model_and_exposes_guided_toolset` passed. The plain async closure and `function_tool(..., name_override="destination_info")` follow the repo's Agents SDK pattern.
- **Notes:** Registration is independent of client construction and environment lookup.

### Automated 6 — Off-loop discipline

- **Criterion:** Run synchronous Tavily search through `asyncio.to_thread` inside `asyncio.wait_for`.
- **Status:** PASS
- **Evidence:** `test_impl_runs_search_off_the_event_loop` passed; `backend/api/concierge.py:839`–`842` contains `wait_for(to_thread(_tavily_search, query), timeout=8.0)`.
- **Notes:** The source and test agree on the required structure.

### Manual 1 — Deployed live check

- **Criterion:** An unpinned Los Angeles weekend query returns one or two current spoken-style sentences without URLs or Markdown.
- **Status:** PASS
- **Evidence:** Deployed revision `vocal-bridge-be-dev-00126-fxd` returned HTTP 200 in 3.49s with two clean sentences naming World Cup watch parties, CicLAvia, concerts, and outdoor screenings. Current World Cup fan zones and the July 19 CicLAvia event were independently corroborated by [Discover Los Angeles](https://www.discoverlosangeles.com/things-to-do/the-best-things-to-do-in-la-this-weekend) and [CicLAvia](https://www.ciclavia.org/). The operator run is also recorded in [live-qa-2026-07-16.md](live-qa-2026-07-16.md).
- **Notes:** No outbound-call quota was used.

### Manual 2 — Trip-aware deployed check

- **Criterion:** A vague destination question on a pinned trip resolves the destination without the traveler naming it.
- **Status:** PASS
- **Evidence:** The operator evidence in [live-qa-2026-07-16.md](live-qa-2026-07-16.md) records a deployed pinned-trip response reflecting Los Angeles. An independent validator-owned synthetic trip with SFO/Mountain View context returned `Visit the Stevens Creek Trail for a walk, the Computer History Museum, and the NASA Ames Visitor Center.` in 6.98s.
- **Notes:** The independent run used a clearly labeled synthetic trip; no unrelated live trip was inspected.

### Manual 3 — Failure honesty

- **Criterion:** With the key absent locally, return the apology and do not stall or error the turn.
- **Status:** PASS
- **Evidence:** With `TAVILY_API_KEY` overridden to empty, direct `destination_info_impl` execution returned the exact fallback in 0.164s with no raised exception. Automated exception and timeout cases also passed.
- **Notes:** The deployed service intentionally retains its configured key, so the absent-key check was local.

### Manual 4 — Latency feel

- **Criterion:** The answer lands within a natural voice pause under the basic-depth/eight-second tool cap.
- **Status:** PASS
- **Evidence:** Independent full `/query` turns completed in 3.49s, 6.98s, and 6.67s. The operator evidence records 9.8s and 6.4s full turns, where the eight-second cap covers the Tavily call rather than both surrounding agent round trips.
- **Notes:** All calls completed without timeout. The subjective threshold should be made numeric; see Gaps.

### Manual 5 — No leakage

- **Criterion:** Destination lookup changes neither booking `pending_options` nor trip items.
- **Status:** PASS
- **Evidence:** On the validator-owned synthetic trip, canonical item-state SHA-256 was `90843799…65cd4` before and after, and canonical `pending_options` SHA-256 was `38e0b9de…a0bed` before and after. [live-qa-2026-07-16.md](live-qa-2026-07-16.md) independently records unchanged state around the operator check. Source inspection shows no write or options-registry call in `destination_info_impl` or `_tavily_search`.
- **Notes:** Hashes were used to avoid reproducing unrelated live option content.

### Tone check

- **Criterion:** Returned strings and instructions are short, spoken-friendly, URL/Markdown/id/tool-name free; failures use the specified apology; use is reactive, not proactive.
- **Status:** FAIL
- **Evidence:** The fallback, live samples, and `BASE_INSTRUCTIONS` reactive-use sentence pass. The independent mocked-answer probe returned `Try **CicLAvia** at www.example.com/events.` unchanged, preserving both Markdown and a bare URL.
- **Notes:** The model instructions cannot repair a string-level contract that the tool itself promises to enforce.

### Definition of done 1 — Automated package

- **Criterion:** All automated assertions pass in the container; suite is green and hermetic without the key.
- **Status:** FAIL
- **Evidence:** The committed suite is green, but Automated 3 fails under an uncovered valid input as documented above.
- **Notes:** A green suite is insufficient where its URL fixture is narrower than the criterion.

### Definition of done 2 — Dependency and image

- **Criterion:** Pin `tavily-python` and successfully build the image.
- **Status:** PASS
- **Evidence:** `backend/requirements.txt:16` pins `tavily-python==0.7.26`. `docker compose build backend` completed successfully and produced image manifest `sha256:8463e799…f715d`.
- **Notes:** Dependency installation was cache-hit; the previously running container also imported and exercised Tavily successfully.

### Definition of done 3 — Cloud Run key

- **Criterion:** Configure `TAVILY_API_KEY` on `vocal-bridge-be-dev` via merge-preserving deployment.
- **Status:** PASS
- **Evidence:** Cloud Run service metadata lists `TAVILY_API_KEY` without exposing its value. Cloud Build `07c446a7-00f7-498c-9705-cf56d646a159` succeeded for commit `3099a6c`; latest ready revision is `vocal-bridge-be-dev-00126-fxd`.
- **Notes:** The deployed live query proves the configured value is usable.

### Definition of done 4 — Manual evidence package

- **Criterion:** Manual checks 1–3 pass and transcript/pytest evidence is saved in the feature directory.
- **Status:** PASS
- **Evidence:** Manual 1–3 pass above. [live-qa-2026-07-16.md](live-qa-2026-07-16.md) contains transcript, deployment, latency, no-leak, and pytest-baseline evidence; this report records the independent rerun.
- **Notes:** Evidence is local/staged at validation time.

### Definition of done 5 — Roadmap close-out

- **Criterion:** Mark Phase 35 complete through the changelog flow, leaving 34 (data-gated) then 24.
- **Status:** FAIL
- **Evidence:** The staged roadmap edit removes `manual QA pending` and leaves Phase 35 marked `[x] COMPLETE`, followed by 34 then 24. Phase 35 nevertheless remains in `specs/roadmap.md`; it has not been archived through the required changelog flow.
- **Notes:** The validator is not authorized to edit the roadmap or changelog.

## Missing tests

- Extend `backend/tests/test_destination_info.py` with `test_search_strips_bare_urls_and_markdown`: supply `Try **CicLAvia** at www.example.com/events.` and assert the result contains neither Markdown delimiters nor a bare/protocol URL.
- Add `backend/tests/test_destination_info.py::test_destination_info_does_not_mutate_booking_or_trip_state`: snapshot `_SESSION_FLIGHT_OPTIONS`, `_LATEST_SEARCH`, and the pinned `TripContext`, call the implementation with a mocked search, and assert byte-equivalent state plus zero repository writes.
- Manual live content, model tool-selection, and latency checks intentionally have no CI test under the requirements' no-live-network rule. Keep recording them in a dated `live-qa-*.md` artifact rather than adding them to the bare suite.

No validator test file was written; the failing sanitizer behavior was demonstrated with a non-network shipping-container probe.

## Gaps in validation.md

- Must “no URLs” include bare domains/`www.` forms, Markdown links, emails, and trailing punctuation, and which Markdown constructs must the tool strip?
- What numeric full-turn threshold defines a “natural voice pause,” and is it measured around `_tavily_search` or the complete `/query` agent turn?
- Must the 600-character cap preserve a complete word and sentence, or is a raw slice acceptable for a spoken result?
- Is changelog archival a prerequisite for validation to pass, or a post-validation action? Requiring it inside this report creates a close-out ordering cycle.
- Should independent validation be required before merge on `vb/feature/*`, or is post-merge validation on `vb/dev` an accepted workflow?

## Risks not covered by validation.md

- Timing out `asyncio.to_thread` does not stop the underlying synchronous Tavily request; a timed-out lookup can continue occupying a worker thread after the fallback is spoken.
- Expected missing-key failures log a full warning traceback on every call, which can add operational noise during local or misconfigured rehearsals.
- The raw 600-character slice can end mid-word or mid-sentence even after URL/Markdown sanitization is corrected.
