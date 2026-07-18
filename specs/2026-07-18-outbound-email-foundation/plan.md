# Plan — Phase 39: Outbound email foundation

Groups 1 and 2–3 are independent (DNS/Resend is manual-operator work; the code
is hermetic without a key) and can proceed in parallel. Group 4 needs both;
group 5 needs group 4.

## 1. Resend account + DNS at Squarespace (operator, runbook-driven)

1.1 Write `dns-runbook.md` in this spec dir: the exact records to **delete**
    (the Squarespace Email Security preset: `v=spf1 -all` on `@`, the
    `p=reject` DMARC, the empty-key `_domainkey`) and to **add**
    (Resend DKIM TXT · SPF on `@`: `v=spf1 include:amazonses.com ~all` ·
    DMARC on `_dmarc`: `v=DMARC1; p=none;` · null MX on `@`: `0 .`), plus the
    standing hazards: A records untouched, never accept a DNS reset prompt,
    one SPF record only.
1.2 Create the Resend account, add domain `talktomytrip.com`, trigger
    verification; copy the exact DKIM record (name + value) into the runbook.
1.3 Apply the runbook at Squarespace: delete the preset records, add the four
    planned records.
1.4 Write `probes/dns_check.py` (this spec dir; stdlib + `dig` subprocess):
    asserts exactly one SPF TXT on `@` with the planned value and no `-all`
    remnant; DMARC `p=none`; a non-empty Resend DKIM key at the selector from
    1.2; null MX `0 .`; `@`/`www` A records still `35.192.205.215`. Nonzero
    exit on any deviation (the `sweep.py` precedent).
1.5 Run `probes/dns_check.py` until green (allow propagation lag), then
    confirm the domain shows **Verified** in the Resend dashboard.

## 2. Send module

2.1 `backend/api/email_client.py`: `send_email(...)` per the requirements
    contract — call-time `RESEND_API_KEY` read → `disabled`; async httpx POST
    to `https://api.resend.com/emails` with 8 s timeout; `From: Cascade
    <info@talktomytrip.com>` constant; optional `reply_to`; try/except guard
    returning `sent`/`error` status dicts, warning-logged failures, never a
    raise.
2.2 `backend/tests/test_email_client.py` (hermetic, `paypal_client` test
    style): missing/empty/whitespace key → `disabled` with no HTTP call;
    2xx → `sent` with id; non-2xx, timeout, and transport error → `error`
    without raising; payload carries from/to/subject/body and `reply_to` only
    when given; key never appears in the returned dict.

## 3. Debug endpoint

3.1 `backend/api/email_api.py`: `POST /test` router — body `{"to": ...}`,
    minimal `@` validation (400 otherwise), canned test message through
    `send_email`, 200 + status dict verbatim.
3.2 Register in `backend/main.py` under prefix `/v1/email` (existing pattern);
    do **not** touch the `access_gate.py` allowlist.
3.3 `backend/tests/test_email_api.py`: gated — 401 without `X-Access-Code`
    when the gate env is set; 200 `disabled` with no key; 200 `sent` with a
    mocked module success; 200 `error` (not a 500) with a mocked failure;
    400 on a bad address.

## 4. Deployment wiring

4.1 Put the Resend key in Secret Manager (`gcloud secrets create
    resend-api-key --data-file=-`) and grant `gemini-service-account`
    secret-accessor on it.
4.2 Mount it: `gcloud run services update vocal-bridge-be-dev --region
    us-west1 --update-secrets=RESEND_API_KEY=resend-api-key:latest`.
4.3 Land the branch via PR to `vb/dev`; confirm the Cloud Build deploy is
    green (pytest-in-image gate included).

## 5. Deployed verification

5.1 Re-run `probes/dns_check.py` (records still as planned) — then curl the
    deployed `POST /v1/email/test` with the access code and a personal
    address.
5.2 Confirm the email arrives; inspect the received headers for
    `spf=pass` and `dkim=pass` (Gmail "Show original" or equivalent).
5.3 Append the dated evidence (curl output, header excerpt, dns_check output)
    to this spec dir as `send-evidence.md`.
