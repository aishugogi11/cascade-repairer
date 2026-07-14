# Requirements — Sabre CERT Exploration (Phase 25)

Roadmap Phase 25. **Explore-only**: size up what the real Sabre developer user + API key
(now in `config/.env` as `SABRE_API_USER_ID` / `SABRE_API_SECRET`) can actually do against
the CERT environment, so the Phase 24 `SABRE_MODE=real` flip is a config change, not a
debugging session. This is the highest-priority open work in the project (Josh, 2026-07-13:
"the most important piece of the entire project to get right").

## Scope

**Full sweep** (spec interview, 2026-07-13): modeled endpoints first, then everything the
credentials are entitled to.

In scope:

1. **Authenticate against CERT** (`https://api.cert.platform.sabre.com`) using the new
   credentials. The real client (`backend/api/sabre/real_client.py`) expects
   `SABRE_BASE_URL` + a pre-built `SABRE_CLIENT_SECRET` (Basic secret for
   `POST /v2/auth/token`, recipe in `specs/2026-07-08-sabre-tools/sabre-api-notes.md`:
   `base64( base64("V1:{EPR}:{PCC}:AA") + ":" + base64(password) )`); `.env` carries the
   raw user id + secret. Bridge the gap **out-of-band** — construct/derive the secret and
   document the recipe — do not edit the client. If the v2 recipe fails, fall back to the
   `POST /v3/auth/token` password grant (username `{EPR}-{PCC}-AA`) and document which
   grant actually works; if only v3 works, that is a Phase 24 finding, not a fix here.
2. **Probe the endpoints the client layer already models**: Bargain Finder Max v5
   (`POST /v5/offers/shop`) and Booking Management `createBooking` / `cancelBooking` /
   `modifyBooking`. Record request/response **deltas against the mock shapes**
   (`backend/api/sabre/shapes.py`, which trace 1:1 to the 2026-07-08 notes).
3. **Sweep the "Try it Out"-flagged REST set** from the kickoff instructions
   (`about/Kickoff _ Instructions for Hackathon.pdf`) across all domains — air (seat maps,
   schedules, availability, exchange/reshop), hotel/lodging, ground/car, utility/content.
   For each: reachable or not, entitlement/authorization errors verbatim, and observed
   rate limits.
4. **Answer the Flight Search API v1 entitlement question** — this gates the backlogged
   deal-manufacturing engine (see `specs/BACKLOG.md`); the answer is a go/no-go input for
   the next replan.
5. **A CERT-marked pytest suite** exercising the real client end-to-end for
   search → create → cancel (see Decisions).
6. **An updated API-notes doc** — successor to
   `specs/2026-07-08-sabre-tools/sabre-api-notes.md`, living in this spec directory as
   `sabre-cert-notes.md`.

Not in scope (stays in Phase 24):

- Flipping `SABRE_MODE=real` anywhere (local default, Cloud Run env).
- Converting real Sabre offset-bearing times to Pacific (the Phase 19 residual).
- **Any edit to `backend/api/sabre/` production code** (spec interview constraint).
  Client bugs found against CERT are *documented* in the notes doc as Phase 24 work items,
  not fixed here. New test files and exploration scripts are allowed; the client is frozen.

## Decisions

(All from the 2026-07-13 spec interview.)

- **Certification artifact is a CERT-marked pytest suite** — a module under
  `backend/tests/` marked `@pytest.mark.cert`, **deselected by default** (pytest.ini
  addopts `-m "not cert"` or equivalent) so hermetic CI never touches the network. Run
  deliberately with env vars supplied. It drives the *existing real client* through
  `search` → `create` → `cancel` against CERT, proving the Phase 24 flip path. Repeatable
  by design because Sabre periodically resets test credentials.
- **Broad-sweep probes are exploration artifacts, not product code** — standalone scripts
  under this spec directory (`probes/`), runnable inside the backend container. Their
  output feeds the notes doc; they carry no maintenance promise.
- **Always cancel test PNRs**: any booking created in CERT is cancelled in the same
  run — `try/finally` in both probes and the pytest suite — so no orphaned test PNRs
  accumulate against the account.
- **Guard against key resets**: a fast auth smoke-check (token request only) is the first
  step of every probe/test session, so a reset credential is detected in seconds rather
  than debugged for an hour. Kickoff caveat: "You may need to create new test credentials
  as they are periodically reset."
- **The notes doc drives the replan**: it must end with a *"What this unlocks for the
  demo"* section — explicit recommendations (deal-engine go/no-go, Phase 24 risk list,
  any newly-discovered API worth demo time) feeding the next `sdd-replan`.

## Context

- **Credentials never leave `config/.env`** — no values in code, notes, fixtures, or
  committed request/response captures. Scrub tokens and secrets from any saved payloads
  (the Phase 12 scrub-helper precedent). Recorded responses in the notes doc are trimmed
  to shape-relevant fields, per the 2026-07-08 notes style.
- **Tone/style of the notes doc**: follow `sabre-api-notes.md` — confidence labels per
  claim, verbatim error payloads where they matter, tables for environment/endpoint
  matrices.
- **Testing conventions**: pytest runs via `docker compose exec` (project convention);
  CI runs the suite hermetically inside the built image — the cert marker must keep it
  that way with zero setup (mirroring the access-gate fail-open pattern).
- **Timeline pressure**: hackathon is 2026-07-18. Phases 22–23 (dashboard) queue behind
  this; the faster the entitlement picture is clear, the sooner the replan can allocate
  remaining days.
- **Known seam to respect**: `SABRE_MODE` is read per call by the dispatcher
  (`backend/api/sabre/client.py`) with per-call fallback to mock — the pytest suite should
  instantiate/exercise the real client directly (or set env only within the test process),
  never by changing defaults.
