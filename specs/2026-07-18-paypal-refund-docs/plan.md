# Phase 38 — Record the PayPal refund: Plan

Documentation-only. Every task group is a Markdown edit; no `backend/` file changes. Groups are
independently implementable, but 1 (verification) feeds the wording of 2–4.

## 1. Verify the remaining claims

1.1. Read `backend/tests/test_paypal_client.py` end to end: confirm the test count (commit says
     13), that the tests are hermetic (no PayPal env vars, no network — the kill-switch/`disabled`
     path plus mocked `httpx` for sent/pending), and note the covered behaviors (delta rules,
     env gating, never-raises, spoken-line shapes) for the changelog's evidence clause.
1.2. Confirm the full-suite count claim ("572 green") by running the suite the CI way:
     `docker compose build backend && docker run --rm vocal-bridge-training-backend python -m pytest tests/ -q`.
     Record the actual number (it may have moved since `b31f594`) in this spec dir.
1.3. Spot-check `requirements.md`'s "Verified facts" table once more against
     `backend/api/paypal_client.py` and `demo.py` on this branch (post-merge state, not the diff)
     — anything that drifted gets corrected in the requirements before it reaches the changelog.

## 2. Changelog entry (`specs/changelog.md`)

2.1. Add a **Phase 38** entry in newest-first position (above Phase 37), following the
     established format: heading, `**Completed:** 2026-07-17` line (merged PR #71 `b31f594`,
     merge `809526f`; live evidence: sandbox payout batch `LJ4CP8V52G7RN`, $0.30; hermetic test
     count from 1.1; suite count from 1.2), credit **Pallavi G**, and link
     `specs/2026-07-18-paypal-refund-docs/`.
2.2. One narrative paragraph covering: the `_maybe_refund_line` seam in `_call_back_with_results`
     (+22 lines, consent/concurrency/repair untouched), the trigger (fixed flight, `rebooked_from`
     fare vs new fare, ≥ $0.01 delta), sandbox Payouts via `paypal_client.py`, the three-env-var
     kill switch (absent = silently off, demo byte-identical), the never-raises/8 s-timeout
     contract (Call 2 always fires), and the pending-path spoken line with the no-retry looseness.

## 3. Tech-stack reference (`specs/tech-stack.md` § Backend)

3.1. Add a new § Backend entry (after the Phase 34 `check_return_flights` entry, matching the
     tool-entry prose style): **"PayPal fare-difference refund (PR #71, Pallavi G, 2026-07-17)"**
     — the seam, trigger conditions, delta rule, `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` /
     `PAYPAL_RECEIVER_EMAIL` (+ optional `PAYPAL_API_BASE`, sandbox default) named explicitly as
     the call-time-read kill switch, the never-raises contract, and the deployment surface
     (`--update-env-vars` merge on Cloud Run, the standing pattern).
3.2. Record the two **accepted loosenesses** in the entry, in the established style: (a) a failed
     payout speaks "refund is processing… shortly" though nothing retries — the demo's honesty
     rides on sandbox reliability; (b) the receiver is a single fixed `PAYPAL_RECEIVER_EMAIL`,
     not a per-traveler address — correct for the single-operator demo.

## 4. README operator run sheet (`README.md`)

4.1. Update step 6 of "Running it live" ("**6. Call 2 arrives** (~35 s after consent) speaking
     the actual rebooked details and price delta."): add that when the rebooked flight is
     *cheaper*, Call 2 also says the difference was refunded to PayPal — and that no refund
     sentence means an equal/pricier fare or the PayPal env vars are unset (the kill switch).
     One or two sentences, run-sheet voice.

## 5. Roadmap close-out & ship

5.1. Confirm the staged `specs/roadmap.md` promotion (the triage paragraph + Phase 38 section) is
     intact on this branch; mark the Phase 38 heading `[x] COMPLETE` when 1–4 are done.
5.2. Store the run evidence (suite output from 1.2, the verified-facts confirmation from 1.1/1.3)
     in this spec dir — **not** in the PR body (standing convention).
5.3. Commit, push, PR into `vb/dev` (Josh merges), targeting merge before the demo. The resulting
     deploy is behavior-neutral; CI's in-container pytest is the free regression check.
