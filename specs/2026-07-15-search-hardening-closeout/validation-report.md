# Validation Report — Search-hardening close-out (Phase 30)

**Branch:** `vb/dev`  
**Commit:** `37fed47cd49fa1d157352d03db8392b4eb116a53`  
**Date:** 2026-07-15

## Summary

**FAIL (historical result; future-workflow remediation applied afterward).** The Phase 30 implementation and hermetic acceptance tests pass: the exact bare-container suite reports 387 passed, 12 skipped, 9 cert tests deselected, and only the seven explicitly allowed warnings. The mock stale-options walkthrough and `git_pull_dev.sh` resolution also pass. The acceptance package nevertheless fails for two independent reasons: PR #47 has an empty description, so Definition-of-Done B's pre-merge evidence requirement is unmet; and the deliberate read-only CERT subset fails because the computed +30-day DFW→LAX search currently returns no priced itineraries. Validation ran on `vb/dev` because the feature had already merged; HEAD is the exact PR #47 merge with no later commit. After this report, the user authorized hardening `git_pull_dev.sh` so future PRs cannot merge without an evidence-bearing description; that remediation cannot retroactively change PR #47 or this result.

## Criterion-by-criterion results

### 1. Suite green

- **Criterion:** Full bare-container suite passes with only the allowed warning baseline.
- **Status:** PASS
- **Evidence:** Ran `docker compose build backend`, then `docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -q`. Result: `387 passed, 12 skipped, 9 deselected, 7 warnings in 5.84s`.
- **Notes:** The warnings are exactly one `StarletteDeprecationWarning` and six pre-existing unawaited-coroutine `RuntimeWarning`s.

### 2. Six-case metro aliases

- **Criterion:** The named test covers NYC→JFK, WAS→IAD, and CHI→ORD in both request positions, including market-check and captured-request assertions.
- **Status:** PASS
- **Evidence:** `backend/tests/test_sabre_instaflights.py:1065` defines all six parameter cases; `:1102-1105` asserts the captured airport codes, successful market check, and optioned response. The targeted bare-container run covering this and the other Phase 30 tests reported `12 passed, 40 deselected`.
- **Notes:** The committed assertions satisfy the literal six-case reading; this is not source-inspection-only evidence.

### 3. POST-path 401 refresh

- **Criterion:** One 401 mints and uses a fresh bearer on a single POST retry; a second 401 raises after exactly one retry.
- **Status:** PASS
- **Evidence:** `backend/tests/test_sabre_instaflights.py:806` checks two token mints, two POST sends, fresh retry authorization, cached fresh token, and result. `:838` checks `httpx.HTTPStatusError` after two POST sends. Both passed in the full and targeted bare-container runs.
- **Notes:** Both tests call `RealSabreClient._post`, not the GET path.

### 4. Stale options cleared

- **Criterion:** Empty, error, and unsupported-market searches clear the current session's option state and prevent a subsequent option-one booking; other-session state survives.
- **Status:** PASS
- **Evidence:** `backend/tests/test_sabre_instaflights.py:423` parameterizes `empty`, `error`, and `unsupported`, then asserts both stores clear and `book_flight_impl(session, 1)` returns the no-options line. `:485` proves another session's `_SESSION_FLIGHT_OPTIONS` and `_LATEST_SEARCH` survive. All four generated tests passed in the targeted run.
- **Notes:** `backend/api/concierge.py:435-476` invokes the ownership-guarded clear on all four non-optioned returns, including missing inputs. The missing-input branch is behaviorally verified below but lacks its own committed regression case.

### 5. Computed dates only

- **Criterion:** No literal travel date was added to a Phase 30 test or fixture.
- **Status:** PASS
- **Evidence:** Diff-scanned added lines in `backend/tests/test_sabre_instaflights.py` for ISO date literals; none were found. The file uses `_DEPART = date.today() + timedelta(days=21)`, `_DAY`, and `_NEXT_DAY` at `:25-27`.
- **Notes:** No validator test was added for this static check.

### 6. Behavior walkthrough — stale options

- **Criterion:** In an ephemeral mock container, a valid search stores options, an all-unmappable search speaks the no-flights line, and option one can no longer book the earlier result.
- **Status:** PASS
- **Evidence:** Ran the walkthrough against the freshly built image with `SABRE_MODE=mock`. State changed from `STATE_AFTER_VALID: True validator-walkthrough` to `STATE_AFTER_NO_RESULTS: False None`. Captured turns:

  ```text
  NO_RESULTS_TURN: I couldn't find any flights for that day — want to try a different date?
  BOOK_AFTER_NO_RESULTS_TURN: I don't have flight options in front of me yet — tell me where you're headed and I'll search first.
  ```

- **Notes:** A second walkthrough also stored options, submitted a missing destination, observed both stores clear, and confirmed option one could not book.

### 7. `git_pull_dev.sh` resolution

- **Criterion:** The default base is `vb/dev`, `BASE_BRANCH=main` overrides it, and the documented resolution order matches.
- **Status:** PASS
- **Evidence:** `bash -n git_pull_dev.sh` passed. Executing only lines 1-41 (stopping before `git add`, push, or merge) printed:

  ```text
  ==> Base branch: vb/dev
  ==> Base branch: main
  ```

  `git_pull_dev.sh:17-35` documents and implements env override → `origin/vb/dev` → GitHub default → `origin/HEAD`.
- **Notes:** At the validated commit, the script had no native dry-run mode, so only its non-mutating resolution prefix was executed. The post-validation remediation below adds one.

### 8. Deliberate CERT run

- **Criterion:** With credentials available, run the read-only auth, supported-markets, real-priced-search, and timezone-parity subset and capture dated output.
- **Status:** FAIL
- **Evidence:** On 2026-07-15, ran the four-test subset against the freshly built image, excluding all PNR-mutating tests. Auth, supported markets, and timezone parity passed. `test_instaflights_search_returns_real_priced_itineraries` failed because `InstaFlightsResponse(PricedItineraries=[])` was returned for computed +30-day DFW→LAX. Result: `1 failed, 3 passed, 5 deselected in 3.65s`.
- **Notes:** This is live CERT content drift, not a Phase 30 hermetic regression, but criterion 8 does not classify that outcome as optional or untestable once credentials are available.

### 9. Tone check

- **Criterion:** The four non-optioned return strings remain byte-identical and no user-facing jargon is introduced.
- **Status:** PASS
- **Evidence:** The production diff for `backend/api/concierge.py` adds only the internal `_clear_search_state` helper and calls to it; no user-facing return string changed. Current strings remain at `backend/api/concierge.py:308-319` and `:445-476`.
- **Notes:** The new helper's prose is internal only.

## Definition-of-done results

- **A — PASS:** Criteria 1-5 exist and pass in the bare-container artifact; the added-date diff check is clean.
- **B — FAIL:** [PR #47](https://github.com/zen-apps/hackathon-vocal-bridge/pull/47) has an empty description. GitHub reports creation at `2026-07-15T13:03:41Z` and merge at `2026-07-15T13:03:44Z`; no §6-8 transcript/output snippets were in the description before merge.
- **C — PASS:** `backend/api/concierge.py:445-476` clears state for missing inputs, unsupported markets, exceptions, and no options. Tests cover the latter three; the validator walkthrough confirmed missing-input behavior.
- **D — PASS:** `git_pull_dev.sh` defaults to `vb/dev`, preserves the env override, and documents the complete resolution order.
- **E — PASS:** `specs/roadmap.md:17` marks Phase 30 `[x] COMPLETE`.

## Validation evidence — post-validation remediation

**Remediation date:** 2026-07-15  
**Remediation branch:** `vb/feature/pr-evidence-guard`  
**Scope:** Future `git_pull_dev.sh` runs; historical PR #47 remains unchanged.

- The original one-argument workflow is now a safe first phase: it commits and pushes, opens a draft PR with an explicit validation-pending description, and exits successfully without merging. This leaves the feature branch and PR available for independent validation.
- The merge phase can begin either by editing the draft PR description in GitHub and rerunning the one-argument command, or by rerunning with a second positional PR-body path / `PR_BODY_FILE`. A supplied file must be non-empty and contain a populated `## Validation evidence` section; placeholder-only evidence is rejected before staging or pushing.
- New PRs use explicit `--title` plus `--body`/`--body-file` arguments instead of `--fill`, so a one-line commit subject can no longer silently become a titled PR with an empty description.
- Existing PRs are checked before merge. A supplied body file updates the PR; without one, the existing remote body must already pass the evidence guard. A failed guard defers the merge.
- Immediately before merge, the script reads the body back from GitHub and refuses to merge if the description is empty or lacks populated validation evidence.
- `DRY_RUN=1` now exercises both phases without mutating git or GitHub: without a body it shows the draft/deferred-merge path; with evidence it prints the planned verification and merge path.
- Invoking the script through `sh` now re-enters Bash when necessary, honoring its declared interpreter.

Dry-run evidence after the remediation:

```text
Missing body: draft PR / deferred-merge path selected; no merge attempted.
Body without a Validation evidence section: rejected before mutation.
Evidence-bearing body: accepted; all commit/push/PR/merge/sync actions printed as DRY RUN only.
```

This closes the future-workflow cause of Definition-of-Done B. It does not turn the historical report into PASS: pre-merge evidence cannot be added retroactively, and the separate live CERT content-drift failure remains.

## Missing tests

- **Missing-input stale state:** No committed test stores options, follows with missing input, and then proves both stores clear plus booking is blocked. Proposed: `backend/tests/test_validator_search_hardening_closeout.py::test_missing_input_clears_stale_options_and_blocks_booking`.
- **Base-branch and PR-evidence workflow:** The script now has a native mutation-free dry-run, but no committed automated shell test. Proposed: `backend/tests/test_git_pull_dev.py::test_base_branch_and_pr_evidence_guards` using a temporary git remote and stubbed `gh` to assert default/override resolution, invalid-body rejection, remote-body verification, and that no merge occurs after a failed guard.
- **Exact copy contract:** Criterion 9 has no automated byte-for-byte assertion for all four strings. Proposed: `backend/tests/test_validator_search_hardening_closeout.py::test_non_optioned_search_copy_contract`, driving each branch and asserting the exact response text.
- **Computed-date guard:** Criterion 5 is enforced only by review/diff inspection. Proposed: `backend/tests/test_validator_docs_contract.py::test_phase30_tests_contain_no_literal_travel_dates`, scanning Phase 30-added test fixtures for literal ISO travel dates.

During the original independent validation, no validator-authored tests were added and this report was the sole file produced. The later user-authorized remediation modifies `git_pull_dev.sh` separately.

## Gaps in validation.md

- Should a live CERT priced-search failure caused by the documented cache/pair drift be `FAIL`, `UNTESTABLE`, or a separately labeled environment failure? Criterion 8 fixes DFW→LAX at +30 days but provides no alternate-pair or retry rule.
- What exactly is a "never-searched slot" in criterion 4: an absent current-session entry, or a different session that has never searched? The committed ownership test clearly covers another session with stored state.
- How should an independent validator prove PR-description evidence was present *before* merge if the body was later edited? The required authoritative timestamp/audit source is unspecified.
- Should Phase 30 remain marked complete when independent validation fails? Definition E currently checks only the literal roadmap marker.

## Risks not covered by validation.md

- At the validated commit, `git_pull_dev.sh` merged with `--admin`; PR #47 was created and merged three seconds later with an empty body and no status checks. The post-validation guard now blocks an empty or evidence-free description before merge, but `--admin` still bypasses branch-protection requirements and remains a separate process risk.
- DFW→LAX remains in the supported-markets list but returned no +30-day content twice during this validation, including from the freshly built image. Any demo or smoke test that assumes this fixed pair/date is currently brittle.
- Validation occurred after merge on `vb/dev`, not on the feature branch. HEAD is the exact merge commit, so no unrelated post-merge code is included, but the process no longer provides pre-merge isolation.
