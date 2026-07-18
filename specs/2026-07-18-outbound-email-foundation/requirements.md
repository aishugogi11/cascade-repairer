# Requirements — Phase 39: Outbound email foundation (talktomytrip.com)

Deliverability foundation for outbound-only transactional email from
`info@talktomytrip.com`, sent by the FastAPI Cloud Run service via **Resend**.
No agent surface — the Concierge says nothing about email in this phase
(that is Phase 40). Shippable and verifiable on its own: the completion bar is
a test send from the deployed service landing in a personal inbox with SPF and
DKIM passing.

## Scope

### In scope

| Deliverable | Shape |
|---|---|
| Send module | `backend/api/email_client.py` — guarded async Resend send, the `paypal_client.py` pattern |
| Debug endpoint | `POST /v1/email/test` (`backend/api/email_api.py`, registered in `backend/main.py`) — access-code-gated test send |
| DNS runbook | `dns-runbook.md` in this spec dir — exact Squarespace records to delete and add |
| DNS verify script | `probes/dns_check.py` in this spec dir — objective live-record check, nonzero exit on deviation |
| Hermetic tests | `backend/tests/test_email_client.py` + `backend/tests/test_email_api.py` — no network, no key |
| Deployment wiring | `RESEND_API_KEY` in GCP Secret Manager, mounted as a Cloud Run env var |

### Send module contract (`email_client.py`)

- `async def send_email(*, to, subject, html=None, text=None, reply_to=None) -> dict`
  returning a status dict — `{"status": "sent", "id": ...}`, `{"status": "disabled"}`,
  or `{"status": "error", "reason": ...}`. **Never raises** — a failed email must
  never kill the calling request (Phase 40 will call this from the booking flow).
- Transport: **Resend HTTP API (`POST https://api.resend.com/emails`) via async
  `httpx`** — not SMTP (Cloud Run blocks port 25; SMTP doesn't fit request-scoped
  lifecycles) and not the `resend` SDK (no new dependency; `httpx==0.28.1` is
  already pinned).
- `From: Cascade <info@talktomytrip.com>` as a module constant; optional
  `reply_to` passthrough.
- **Kill switch:** `RESEND_API_KEY` read **at call time**, whitespace-stripped;
  missing/empty → status `disabled`, no HTTP call, no exception — which is also
  what keeps the hermetic tests credential-free (the `paypal_client.py` trio
  precedent).
- 8 s `httpx` timeout (the standing external-call ceiling: Tavily, PayPal).
  Timeout, non-2xx, and transport errors all log a warning with detail and
  return status `error`.

### Debug endpoint contract (`POST /v1/email/test`)

- Body `{"to": "<address>"}`; sends a canned test message ("Cascade test send"
  subject, one-line body naming the service) through the send module.
- Returns HTTP 200 with the module's status dict verbatim — `disabled` and
  `error` are honest visible outcomes, not 500s. A `to` without `@` → 400
  (plain check; no `email-validator` dependency).
- **Not** on the `access_gate.py` allowlist — it inherits the `X-Access-Code`
  gate automatically, so it is safe to leave in place after the event and
  reusable for the morning smoke.

### Out of scope

- Any agent/Concierge surface, spoken offers, or email-address storage (Phase 40).
- Inbound mail, reply handling, bounce/complaint webhooks.
- Email templates beyond the canned test message (Phase 40 owns itinerary/repair content).
- DMARC tightening past `p=none` (later, at volume — rollout checklist tail).
- Background-task/Cloud Tasks send path — inline await is the decision (below);
  revisit only if sends measurably block.

## Decisions

- **Resend, not Google Workspace SMTP or SES direct** (TODO, verbatim): runs on
  AWS SES, ~3,000 emails/month free, async HTTP API, ~10-min setup. SES direct
  is the at-volume alternative with AWS-account + sandbox friction we don't want
  on event day.
- **Async inline send + Secret Manager** (spec interview): `await` the httpx
  call inside the request under the try/except guard; `RESEND_API_KEY` lives in
  Secret Manager and reaches the service as an env var
  (`--update-secrets=RESEND_API_KEY=resend-api-key:latest` — a merge, survives
  redeploys like `--update-env-vars`). Never in the image.
- **Gated debug endpoint** (spec interview): deployed verification is a curl
  against `/v1/email/test` with the access code — no ad-hoc container execs,
  and the endpoint doubles as the event-morning email smoke.
- **DNS runbook + verify script** (spec interview): the Squarespace edits are
  manual, so validation gets an objective check — `probes/dns_check.py` (stdlib
  + `dig` subprocess, no new dependency; the `sweep.py` exit-code precedent)
  confirms the live records match the plan before the test send is attempted.
- **Replace, don't add** (triage finding, 2026-07-18): the domain's current
  Squarespace "Email Security" preset (`v=spf1 -all` on `@`, DMARC
  `p=reject; sp=reject; adkim=s; aspf=s`, `_domainkey` with an **empty** DKIM
  key) hard-fails all mail from the domain today and directly conflicts with
  the planned records. Those records must be **removed/replaced**, not added
  alongside — two SPF TXTs on `@` is itself a failure mode.

## Context

- **Event-day phase** (July 18): smallest-possible, low-risk build — the demo
  must not depend on it, and a failed email may never break anything else.
  Hence the never-raise guard and the disabled-by-default posture in every
  key-less environment (local dev, CI, hermetic tests run exactly as today).
- **Patterns to follow:** `paypal_client.py` (call-time env reads, never-raise
  guard, 8 s timeout, credential-free hermetic tests), `access_gate.py`
  (gated-by-default routing), router registration in `backend/main.py` with a
  `/v1/email` prefix, tests run via `docker compose exec` in the container.
- **DNS hazards** (runbook must state them): leave the existing A records
  (`@`/`www` → `35.192.205.215`, the nginx SSL proxy → Cascade app) untouched;
  never accept a Squarespace "reset DNS to defaults" prompt; exactly one SPF
  TXT on `@`; null MX `0 .` on `@` (outbound-only — no inbound mail).
- **Tone:** the only user-visible copy is the canned test email — keep it
  minimal and honest (it names the service and says it is a deliverability
  test; no marketing language).
- Per the 2026-07-16 evening replan: run evidence lives in this spec dir and
  the changelog entry — `validation.md` must not require PR-body evidence.
