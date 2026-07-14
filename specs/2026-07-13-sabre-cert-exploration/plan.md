# Plan — Sabre CERT Exploration (Phase 25)

Task groups are ordered but largely independent after Group 1 (auth is the gate for
everything). Every group that touches CERT starts with the auth smoke check and ends
with zero PNRs left behind.

## 1. Auth bootstrap

1.1 Read the kickoff PDF's credential/auth section and the Sabre Developer Hub
    authentication docs; confirm which grant the developer-user credentials support
    (v2 client_credentials with constructed Basic secret vs. v3 password grant).
1.2 Write `probes/auth_check.py` (this spec dir): builds the auth material from
    `SABRE_API_USER_ID` / `SABRE_API_SECRET` in `config/.env`, requests a token from
    CERT, prints token metadata only (never the token itself), exits nonzero on failure.
    This is the key-reset smoke check every later session starts with.
1.3 Document the working recipe in `sabre-cert-notes.md` § Auth — including the exact
    env-var bridge for Phase 24 (how `SABRE_BASE_URL` + `SABRE_CLIENT_SECRET` get
    derived/set for the unmodified real client, e.g. a documented export line or a
    derivation snippet). If only the v3 grant works, record that the real client needs a
    Phase 24 change and specify it precisely; do not edit the client.

## 2. Modeled-endpoint probes (BFM search + Booking Management)

2.1 `probes/bfm_search.py`: `POST /v5/offers/shop` with the notes' request shape
    (MSP → SFO-style single-slice). Save a scrubbed, trimmed response; diff against
    `shapes.py` expectations; record deltas.
2.2 `probes/booking_lifecycle.py`: `createBooking` → (optionally `modifyBooking`) →
    `cancelBooking`, with the cancel in a `finally` block keyed on any successfully
    created confirmation ref. Record response deltas, confirmation-ref format, and
    whether the unticketed cancel+create rebook path behaves as the 2026-07-08 notes
    predicted.
2.3 Note every mismatch between CERT reality and the mock client's deterministic shapes
    as an explicit Phase 24 work item in the notes doc (client is frozen this phase).

## 3. Entitlement sweep ("Try it Out" REST set)

3.1 From the kickoff PDF and the Developer Hub reference index, enumerate the
    Try-it-Out-flagged REST APIs into a checklist (air / hotel / ground / utility).
3.2 `probes/sweep.py`: for each candidate endpoint, issue a minimal valid request;
    classify the result — works / entitled-but-bad-request / not entitled (401/403) /
    rate-limited — capturing verbatim error bodies. Read-only endpoints only; anything
    that creates state gets the Group 2 try/finally treatment or is probed manually.
3.3 **Flight Search API v1 specifically**: determine entitlement and, if entitled, a
    minimal working call — this is the deal-engine gate answer.
3.4 Record observed rate limits / concurrency ceilings and the entitlement matrix in the
    notes doc.

## 4. CERT-marked pytest certification suite

4.1 Add the `cert` marker to `backend/pytest.ini` and deselect it by default so the
    hermetic CI suite is untouched (verify: full suite passes with no Sabre env vars).
4.2 `backend/tests/test_sabre_cert.py`, all tests `@pytest.mark.cert`:
    skip with a clear reason unless the required env vars are present; module fixture
    runs the auth smoke check first (fail fast on reset keys).
4.3 Test flow through the **unmodified real client**: `search` (BFM v5) → `create` →
    `cancel`, asserting responses validate against `shapes.py` and the cancel actually
    lands (finally-guaranteed). Assert no mock fallback occurred if exercised via the
    dispatcher.
4.4 Document the run command (docker compose exec + env plumbing from `config/.env`) at
    the top of the test module and in the notes doc, so it's re-runnable after any
    credential reset and on event-day morning.

## 5. Notes doc + replan handoff

5.1 Write `sabre-cert-notes.md` (this spec dir) as the successor to
    `specs/2026-07-08-sabre-tools/sabre-api-notes.md`: auth recipe, endpoint matrix,
    request/response deltas vs. mock shapes, entitlements + rate limits, Flight Search v1
    answer, Phase 24 work-item list (client changes needed, if any).
5.2 End with **"What this unlocks for the demo"**: deal-engine go/no-go recommendation,
    Phase 24 risk list, and any discovered API worth demo time — the direct input to the
    next `sdd-replan`.
5.3 Cross-link: add a pointer from the old notes doc header to the new one.
