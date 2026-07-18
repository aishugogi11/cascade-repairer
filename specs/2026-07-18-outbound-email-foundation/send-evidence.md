# Send evidence — Phase 39 deployed verification (2026-07-18)

## Deployed test send (validation Manual-3)

`POST /v1/email/test` on `vocal-bridge-be-dev` (access code attached, code not
reproduced here), recipient `joshjanzen@gmail.com`, 2026-07-18 morning PT:

```
{"status":"sent","id":"ec71d0d6-b0d0-486a-88f1-04cb36f1a862"}
HTTP 200
```

Full path exercised: Cloud Run → `email_client.send_email` → `RESEND_API_KEY`
env → Resend API → `Cascade <info@talktomytrip.com>`.

Operator's independent direct-API send the same morning (laptop curl straight
to `api.resend.com`, from `hello@talktomytrip.com`) also delivered to the
Gmail inbox — screenshot evidence in the PR conversation; proves domain
verification and arbitrary local-parts on the verified domain.

## DNS state at verification (validation Manual-1) — dns_check.py output

```
[FAIL] SPF count: 0 SPF record(s) on @ (need exactly 1): []
[PASS] SPF preset gone: no 'v=spf1 -all' hard-fail record remains
[PASS] DMARC count: 1 DMARC record(s): ['v=DMARC1; p=none;']
[PASS] DMARC policy: v=DMARC1; p=none;
[PASS] DKIM key: resend._domainkey.talktomytrip.com: non-empty p= key
[FAIL] Null MX: [] (want ['0 .'])
[PASS] A talktomytrip.com: ['35.192.205.215'] (want ['35.192.205.215'])
[PASS] A www.talktomytrip.com: ['35.192.205.215'] (want ['35.192.205.215'])
DEVIATION: 2 check(s) failed: SPF count, Null MX
```

The blocking preset records are **gone** (hard-fail SPF, `p=reject` DMARC,
empty DKIM key) and delivery works — Resend authenticates via DKIM plus SPF
on its `send.` return-path subdomain, so the missing apex records don't
block sending. Two planned records remain unapplied at Squarespace:

- **Apex SPF** (`@` TXT `v=spf1 include:amazonses.com ~all`) — planned
  hygiene; not used for authentication on Resend's return-path.
- **Null MX** (`@` MX `0 .`) — worth adding: with *no* MX record, RFC 5321
  falls inbound delivery attempts back to the A record, i.e. the nginx
  demo proxy at 35.192.205.215; the null MX declares "no inbound mail"
  explicitly.

## SPF/DKIM headers (validation Manual-4)

*(Operator: paste the Gmail "Show original" authentication excerpt for the
"Cascade test send" message here — expect `dkim=pass` for talktomytrip.com
and `spf=pass` for the `send.talktomytrip.com` return-path.)*

## Deployment deviation noted

`RESEND_API_KEY` is set as a **plain env var** on the service, not the
spec-decided Secret Manager mount (`--update-secrets`). Functionally
identical at demo scale and consistent with the PayPal-trio precedent;
either accept (record at the close-out replan) or switch later with
`--update-secrets=RESEND_API_KEY=resend-api-key:latest`.
