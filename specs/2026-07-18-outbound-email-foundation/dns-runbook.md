# DNS runbook — talktomytrip.com outbound email (Phase 39)

Operator steps at **Squarespace → Settings → Domains → talktomytrip.com → DNS
settings**. Goal: replace the "Email Security" preset (which hard-fails all
mail from the domain) with the Resend deliverability records.

## Standing hazards — read before touching anything

- **Never accept a Squarespace "reset DNS to defaults" prompt.** It would wipe
  the A records that serve the live demo.
- **Leave the A records untouched:** `@` → `35.192.205.215` and
  `www` → `35.192.205.215` (the nginx SSL proxy → Cascade app).
- **Exactly one SPF TXT on `@`.** Two SPF records is itself a hard failure
  mode — the old one must be *deleted*, not left alongside the new one.

## Step 1 — Resend side first

1. Create the Resend account (free tier) and add domain `talktomytrip.com`
   (Resend dashboard → Domains → Add Domain; region default is fine).
2. Resend shows the DNS records it wants. Copy the **DKIM TXT** record exactly
   (host + value). Record it here before editing DNS:
   - DKIM host: `resend._domainkey` *(confirm against the dashboard; fill in
     the actual selector if it differs)*
   - DKIM value: `p=...` *(fill in from the dashboard)*

## Step 2 — Delete the Email Security preset records

Remove these three existing records (they hard-fail all mail and conflict
with the records below):

| Host | Type | Current value (to delete) |
|---|---|---|
| `@` | TXT | `v=spf1 -all` |
| `_dmarc` | TXT | `v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s` |
| `*._domainkey` (or similar) | TXT | `v=DKIM1; p=` (empty key) |

## Step 3 — Add the planned records

| Host | Type | Priority | Value |
|---|---|---|---|
| *(from Resend, e.g.)* `resend._domainkey` | TXT | — | *(DKIM value from Step 1)* |
| `@` | TXT | — | `v=spf1 include:amazonses.com ~all` |
| `_dmarc` | TXT | — | `v=DMARC1; p=none;` |
| `@` | MX | `0` | `.` *(null MX — outbound-only, no inbound mail)* |

Note: Resend may also ask for an SPF/MX pair on a `send` subdomain (its
bounce/return-path host) — add whatever the dashboard lists; those live on a
subdomain and don't conflict with the `@` records above.

## Step 4 — Verify

1. Wait for propagation (minutes to ~1 hour on Squarespace).
2. Run the objective check (from the repo root; add
   `--dkim-selector <name>` if Resend's selector isn't `resend`):

   ```bash
   python3 specs/2026-07-18-outbound-email-foundation/probes/dns_check.py
   ```

   It exits 0 only when every planned record is live and every preset
   remnant is gone.
3. Back in the Resend dashboard, click **Verify** — the domain must show
   **Verified** before any send is attempted.

## Later (at volume, not event day)

Tighten DMARC gradually: `p=none` → `p=quarantine` → `p=reject`.
