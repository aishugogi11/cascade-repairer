# Phase 38 — Record the PayPal refund: Validation

Documentation-only phase: validation is accuracy-against-code plus the standing hermetic suite.
Per the 2026-07-16 evening replan, **no PR-body evidence is required** — evidence lives in this
spec dir.

## Automated

- **Full suite green, the CI way** (inside the built container — the standing command):
  `docker compose build backend && docker run --rm vocal-bridge-training-backend python -m pytest tests/ -q`
  — zero failures. (Docs-only change; this is the regression check that nothing else moved, and
  it re-verifies the hermeticity claim: the suite passes with no PayPal env vars set.)
- **Docs-contract suite** (`backend/tests/test_validator_docs_contract.py`) passes from a full
  checkout — the changelog/roadmap edits must not break its structural assertions.
- **Specific assertions** (grep-level, from the full checkout):
  - `specs/changelog.md` contains a `## Phase 38` heading positioned above the Phase 37 entry,
    a `**Completed:** 2026-07-17` line, the strings `Pallavi`, `#71`, `LJ4CP8V52G7RN`, and a
    link to `2026-07-18-paypal-refund-docs/`.
  - `specs/tech-stack.md` § Backend names all four env vars: `PAYPAL_CLIENT_ID`,
    `PAYPAL_CLIENT_SECRET`, `PAYPAL_RECEIVER_EMAIL`, `PAYPAL_API_BASE`.
  - `README.md`'s run-sheet step 6 mentions the refund sentence and the kill-switch reading of
    its absence.
  - `specs/roadmap.md`'s Phase 38 heading is marked `[x] COMPLETE`.

## Manual

- **Accuracy read-through** (the core check): with `backend/api/paypal_client.py` and
  `backend/api/demo.py` open beside the three edited docs, confirm every documented claim is
  true of the code as merged — trigger conditions (`fixed` flight, `rebooked_from.price`),
  delta rule (≥ $0.01, old > 0, new ≥ 0), env-var names and call-time reads, sandbox-default
  base URL, 8 s timeout, never-raises, the pending-path spoken line, and that **no claim from
  the commit message survived unverified** (test count and suite count are the ones most likely
  to have drifted).
- **Honesty check:** both accepted loosenesses (pending speaks "processing" with no retry
  machinery; single fixed receiver email) appear in the tech-stack entry — not softened away.
- **No-code check:** `git diff vb/dev...HEAD --stat` shows only `specs/**`, `README.md`, and
  nothing under `backend/`.
- **Run-sheet walkthrough:** read the updated step 6 as the operator would minutes before the
  demo — it must set the expectation for *both* outcomes (refund sentence vs none) in one or
  two sentences without breaking the run sheet's terse voice.

## Tone check

- Changelog and tech-stack entries match the surrounding dense, dated, decision-annotated
  constitution voice (PT dates, bolded decisions, parenthetical evidence).
- The README addition stays in the run sheet's imperative operator voice; no marketing language
  around the PayPal beat.
- Pallavi G is credited in both the changelog entry and the tech-stack reference.

## Definition of done

- All automated assertions pass; the manual read-through found every claim code-true.
- Run evidence (suite output, verified-facts confirmation) stored in this spec dir.
- PR merged into `vb/dev` (Josh merges) with the behavior-neutral deploy green — targeted before
  the live demo so the constitution describes what Call 2 actually says.
- `specs/roadmap.md` Phase 38 marked `[x] COMPLETE`; open order becomes **36 → 24**.
