# Phase 38 — Run evidence (2026-07-18, event morning)

Per the standing convention, run evidence lives here, not in the PR body.

## Full suite, the CI way (inside the built container)

```
docker compose build backend
docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -q
560 passed, 12 skipped, 11 deselected, 7 warnings in 13.20s
```

- 560 passed + 12 skipped = **572 collected non-deselected** — consistent with PR #71's
  "full suite 572 green" claim; the 11 deselected are the `cert`-marked live Sabre tests
  (`addopts = -m "not cert"`, the standing fence).
- The suite ran with **no PayPal env vars set**, re-verifying the hermeticity claim: the
  kill switch (`disabled` path) is what keeps `test_paypal_client.py` credential-free.

## Targeted PayPal tests

```
docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/test_paypal_client.py -q
13 passed in 0.93s
```

- Exactly **13 tests**, verified by read-through 2026-07-18: 4 × `compute_refund_delta`
  (positive delta, pricier-flight None, missing/garbage fares, sub-cent noise), 2 × env
  gating (`disabled` without env + silent, `skipped` on no savings), 3 × payout path via
  `httpx.MockTransport` (sent with batch id + correct wire body, HTTP-500 → `pending`
  never raises, ConnectError → `pending`), 1 × spoken-line shapes (sent/pending speak,
  skipped/disabled silent), 3 × the `demo.py` seam (`_maybe_refund_line`: appends on
  cheaper fixed flight, silent + no client call when not `fixed`, silent without
  `rebooked_from` — the seed-trip case).

## Verified-facts confirmation (plan 1.3)

`backend/api/paypal_client.py` and `backend/api/demo.py` re-read on this branch
(post-merge state) 2026-07-18: every fact in `requirements.md` § Verified facts holds —
trigger conditions (`fixed` flight, `details.rebooked_from.price`), delta rule
(parseable fares, old > 0, new ≥ 0, ≥ $0.01), env-var trio kill switch with call-time
whitespace-stripped reads, optional `PAYPAL_API_BASE` (sandbox default), 8 s timeout,
never-raises broad except → `pending` with the "processing" spoken line, no retry
machinery behind the `reason` string.

## Tooling note (found during validation, fixed in this PR)

The README § "Build & run locally" test command referenced the image tag
`vocal-bridge-training-backend` — a stale pre-rename relic (the compose project now
builds `hackathon-vocal-bridge-backend`; the old tag's image on this machine dated from
2026-07-08 and silently ran a 162-test July-8 suite). The README command is corrected to
the current tag in this PR's step-4 edit; anyone who ran the documented command got a
green-but-stale result, which is exactly the kind of silent drift the morning-smoke items
exist to catch.
