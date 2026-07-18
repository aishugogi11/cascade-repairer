# Validation — Phase 39: Outbound email foundation

Per the 2026-07-16 evening replan: run evidence lives in this spec dir and the
changelog entry — no PR-body evidence is required anywhere below.

## Automated

Run the bare suite in the container (the standing path):
`docker compose exec backend pytest` — green, including the new tests, with
**no** `RESEND_API_KEY` set anywhere in the environment.

Specific assertions that must exist and pass:

1. **Kill switch:** `send_email` with `RESEND_API_KEY` unset, empty, or
   whitespace returns `{"status": "disabled"}` and makes **no** HTTP call
   (mocked transport asserts zero requests).
2. **Never raises:** a non-2xx Resend response, an `httpx.TimeoutException`,
   and a transport error each return status `error` — the test fails if any
   exception escapes `send_email`.
3. **Payload shape:** a mocked 2xx send captures the request — `from` is
   `Cascade <info@talktomytrip.com>`, `to`/`subject`/body match the call,
   `reply_to` present only when passed, and the API key appears only in the
   `Authorization` header (never in the returned status dict).
4. **Endpoint gate:** with the gate env set, `POST /v1/email/test` without
   `X-Access-Code` → 401; with the code → 200.
5. **Endpoint honesty:** mocked module success → 200 `{"status": "sent", ...}`;
   mocked failure → 200 `{"status": "error", ...}` (asserted **not** 500);
   no key → 200 `{"status": "disabled"}`; `to` without `@` → 400.
6. **Hermeticity preserved:** the full bare suite needs no new env vars and
   touches no network (the new tests mock at the httpx boundary).

## Manual

1. **DNS records match the plan:** `probes/dns_check.py` exits 0 against live
   DNS — one SPF TXT on `@` (`v=spf1 include:amazonses.com ~all`), DMARC
   `v=DMARC1; p=none;`, non-empty Resend DKIM key, null MX `0 .`, and the
   `@`/`www` A records still `35.192.205.215`. The old `-all` / `p=reject` /
   empty-DKIM preset records are gone.
2. **Resend shows the domain Verified.**
3. **Deployed test send:** curl `POST /v1/email/test` on
   `vocal-bridge-be-dev` with the access code and a personal address →
   response `{"status": "sent", ...}` and the email arrives in the inbox
   (not spam).
4. **Authentication passes:** the received message's headers show `spf=pass`
   and `dkim=pass` for the sending domain.
5. **Failure honesty:** one deliberate failure (e.g. temporarily bad key via
   env, or an obviously undeliverable Resend-rejected payload) returns 200
   with status `error`/`disabled` — never a 500 — and logs a warning.
6. **No demo regression:** the cascade page and booking flow behave exactly
   as before (no code path outside the new module/router changed; a quick
   `/v1/cascade/` load confirms).

## Tone check

The canned test email is the only user-visible copy: it must name the service,
say it is a deliverability test, and contain nothing else — no marketing
language, no links.

## Definition of done

- All automated assertions above pass in the container with no email env vars.
- Domain verified in Resend; `dns_check.py` green against live DNS.
- The deployed service's test send lands in a personal inbox with SPF and
  DKIM passing, and the dated evidence (curl output, header excerpt,
  dns_check output) is committed to this spec dir as `send-evidence.md`.
- The agent says nothing about email anywhere — Phase 40's surface is
  untouched.
