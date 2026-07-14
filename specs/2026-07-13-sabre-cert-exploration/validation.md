# Validation — Sabre CERT Exploration (Phase 25)

## Automated

- Full hermetic suite still green with **no Sabre env vars set**:
  `docker compose exec backend pytest` — the `cert` marker is deselected by default and
  no collected test attempts network access. This is the CI-safety assertion.
- `pytest -m cert` with credentials supplied (documented run command) passes end-to-end
  against CERT: auth smoke check → BFM v5 search → createBooking → cancelBooking, all
  through the unmodified real client, responses validating against
  `backend/api/sabre/shapes.py` (or failures precisely documented as Phase 24 items —
  a shape mismatch is an acceptable *finding*, an unexplained test error is not).
- Cancel-guarantee assertion: the suite's create test cannot leave a PNR behind on
  failure (finally-path covered, verified by inspection + a forced-failure dry run).
- `git diff vb/dev -- backend/api/sabre/` is **empty** (zero production-code changes;
  new files under `backend/tests/` and `specs/.../probes/` only).
- No credential material committed: grep the branch diff for the values in `config/.env`
  (user id, secret, any captured tokens) — zero hits; `.env` itself untouched by the diff.

## Manual

- **Auth**: `probes/auth_check.py` returns a token against CERT; the notes doc's recipe
  is reproducible from scratch (tested by re-running after deleting any cached state).
  The Phase 24 env-var bridge (`SABRE_BASE_URL` / `SABRE_CLIENT_SECRET` derivation) is
  written down precisely enough that flipping `SABRE_MODE=real` needs no research.
- **Notes doc completeness** (`sabre-cert-notes.md`), checked section by section:
  - Auth recipe with the grant that actually worked (and the one that didn't, if tried).
  - Endpoint/entitlement matrix covering the modeled endpoints **and** the Try-it-Out
    sweep, each row classified (works / not entitled / errored) with verbatim errors.
  - Request/response deltas vs. mock shapes, each delta tagged as a Phase 24 work item
    or explicitly harmless.
  - Observed rate limits and the credentials-reset caveat with the re-bootstrap steps.
  - **The Flight Search API v1 entitlement question has a definite answer** (yes/no/
    blocked-because-X) — this is the single most load-bearing finding.
  - Final **"What this unlocks for the demo"** section with a deal-engine go/no-go
    recommendation and a Phase 24 risk list — concrete enough to drive the next replan
    without re-reading the whole doc.
- **PNR hygiene**: after all probe/test sessions, no lingering test bookings — verify by
  a final Booking Management read (or cancel-again returning already-cancelled) for every
  confirmation ref recorded during the phase.
- **Repeatability**: a second `pytest -m cert` run on a different day (or after a
  credential reset) succeeds using only the documented steps.

## Tone check

Not applicable — no user-facing copy. The notes doc follows the 2026-07-08 notes style:
confidence labels, trimmed payloads, tables.

## Definition of done

1. CERT auth works and is documented reproducibly, including the exact Phase 24
   env bridge for the unmodified real client.
2. Search + create + cancel proven against CERT through the real client via the
   CERT-marked pytest suite; hermetic CI provably unaffected.
3. The entitlement sweep and the Flight Search v1 answer are recorded in
   `sabre-cert-notes.md`, ending with demo-unlock recommendations for the replan.
4. Zero changes under `backend/api/sabre/`, zero committed secrets, zero orphaned PNRs.
5. Phase 25 marked `[x] COMPLETE` in `specs/roadmap.md` only after all of the above.
