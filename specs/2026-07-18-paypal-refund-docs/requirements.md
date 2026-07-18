# Phase 38 — Record the PayPal refund (changelog + constitution reference): Requirements

Documentation-only reconciliation of already-shipped, already-live-verified work: Pallavi G's
PayPal fare-difference refund (PR #71, commit `b31f594`, merged to `vb/dev` 2026-07-17 and
deployed). The constitution and operator docs must describe the demo the judges hear **today**
(2026-07-18, event day): when the repair lands a cheaper flight, Call 2 now speaks a refund
sentence. No backend code changes.

## Scope

**In scope — three surfaces (settled at the spec interview):**

| Surface | Change |
|---------|--------|
| `specs/changelog.md` | A **Phase 38-numbered entry** (newest-first position) archiving the PayPal refund, completed 2026-07-17, credited to Pallavi G (PR #71), linking this spec dir |
| `specs/tech-stack.md` § Backend | A new entry for `paypal_client.py` + the `_maybe_refund_line` seam in `demo.py`: behavior, env-var kill switch by name, the never-raises contract, accepted loosenesses |
| `README.md` operator run sheet | One-line update to step 6 ("Call 2 arrives…") so the operator expects the refund sentence on cheaper-fare repairs (and knows its absence means equal/pricier fare or the kill switch) |

Also in scope: `specs/roadmap.md` — the staged Phase 38 promotion paragraph rides this branch
(decision below), and the phase is marked `[x] COMPLETE` at implementation close per the SDD
convention.

**Out of scope:**
- Any change under `backend/` — the code is shipped, tested (13 hermetic tests, suite 572 green),
  and live-verified; this phase only documents it.
- `specs/mission.md` — scope and audience did not move.
- The untriaged email-spec item in `TODO.md` (separate future triage).
- Any PayPal behavior change, retry machinery, or env-var/secret provisioning.

## Verified facts (source of truth: the code, read 2026-07-18)

The changelog and tech-stack entries must state these **as verified**, not as commit-message
claims. From `backend/api/paypal_client.py` and the `b31f594` diff of `backend/api/demo.py`:

- **Seam:** `_call_back_with_results` calls `_maybe_refund_line(items)` after building Call 2's
  purpose; a returned sentence is appended (`purpose + " " + refund_line`). Consent, concurrency,
  and repair paths untouched (+22 lines in `demo.py`).
- **Trigger conditions:** a `flight` item with status exactly `fixed`; original fare read from
  `details.rebooked_from.price` (the Phase 32 stamp), new fare from `flight.price`, currency
  `flight.currency or "USD"`. No flight / not fixed / no original fare → `None`, no sentence.
- **Delta rule:** `compute_refund_delta` — both fares must coerce to float, old > 0, new ≥ 0,
  and the rounded difference ≥ $0.01; otherwise `skipped` (no sentence). Equal or pricier
  rebooking speaks nothing.
- **Kill switch:** `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_RECEIVER_EMAIL` all
  required (call-time reads, whitespace-stripped); any missing → status `disabled`, no sentence,
  **demo byte-identical**. `PAYPAL_API_BASE` optional, defaults to the PayPal sandbox
  (`api-m.sandbox.paypal.com`).
- **Never-raises contract:** `refund_fare_difference` catches everything; an 8 s `httpx` timeout
  keeps a payout from ever stalling the results callback; Call 2 always fires.
- **Pending nuance (document honestly):** a *failed* payout returns `pending` and **still speaks
  a line** — "…the PayPal refund is processing — they will see it shortly." No retry machinery
  exists; the `reason` string's "will retry outside the demo path" is aspirational. This is an
  accepted looseness to record, mirroring the tech-stack's existing accepted-looseness style.
- **Live evidence:** sandbox payout batch `LJ4CP8V52G7RN` ($0.30), 2026-07-17.
- To re-verify at implementation time: `backend/tests/test_paypal_client.py` exists with 13
  hermetic tests (no PayPal env vars needed — the kill switch makes the suite hermetic).

## Decisions (from the spec interview)

1. **All three surfaces** — changelog, tech-stack, README run sheet — change in this one phase,
   one branch, one PR. The README edit is included because the run sheet scripts the operator's
   expectations for Call 2 and would otherwise be wrong on event day.
2. **Phase 38-numbered changelog entry, code-verified** — framed as the numbered phase (the
   roadmap promotion made it one), completed 2026-07-17 (the merge date of the work it records),
   with every claim checked against the code, not the commit message. Pallavi G credited by name.
3. **Full detail, ship this morning** — env vars named explicitly (the `TAVILY_API_KEY`
   precedent), dense constitution prose style, and the PR targets merge before the live demo so
   the constitution matches what judges hear. The deploy this triggers is behavior-neutral
   (docs + specs only), and CI still runs the full suite as a free regression check.
4. **The staged roadmap promotion rides this branch** — the Phase 38 roadmap entry (staged during
   the 2026-07-18 triage, uncommitted) lands with this PR rather than as a separate vb/dev commit.
5. **Skill-mechanics note:** the roadmap scoped these edits "via `sdd-changelog` / `sdd-replan`";
   settled here that this feature branch carries both edits directly, following those skills'
   *conventions* (newest-first changelog format; tech-stack reconciliation to shipped reality)
   without separate invocations — one small PR beats three ceremonies on event morning.

## Context

- **Style:** match the existing dense, decision-annotated constitution voice — dated entries,
  bolded decisions, parenthetical evidence, PT dates. The changelog entry follows the exact
  format of the Phase 34–37 entries (heading, `**Completed:**` line with evidence and spec link,
  one narrative paragraph).
- **Honesty rule:** the tech-stack entry records what the code *does*, including the pending-path
  spoken line and the no-retry reality — the constitution's credibility comes from documenting
  loosenesses, not hiding them (see the Phase 34/35 accepted-looseness precedents).
- **Attribution:** this is Pallavi's feature — the changelog entry and tech-stack reference name
  her, as the commit does.
- **Standing constraint:** per the 2026-07-16 evening replan, `validation.md` must **not** require
  PR-body evidence — run evidence lives in this spec dir and the changelog entry.
- **Event-day framing:** the refund beat is a sponsor-award-relevant demo moment (PayPal), which
  is why the constitution reference jumps the queue ahead of Phases 36/24.
