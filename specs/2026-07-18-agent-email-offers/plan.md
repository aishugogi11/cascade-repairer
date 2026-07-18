# Plan — Phase 40: Agent email offers

Task groups in build order; each is independently implementable and testable.
Branch: `vb/feature/agent-email-offers`.

## 1. Trip-email registry + content builders

1.1 `backend/api/trip_emails.py` — the in-memory per-trip address registry
    (the `consent.py` module-state precedent): `store(trip_id, address)`,
    `get(trip_id) -> Optional[str]`, `clear(trip_id)`, plus a test-only
    `_reset()`. Addresses normalized on store (strip + lowercase). No
    repository writes, no locks needed (single event loop, single instance).

1.2 `backend/api/email_content.py` — pure builders, no I/O (the
    `call_purposes.py` precedent):
    - `build_itinerary_email(trip, items) -> (subject, html, text)` — trip
      title/route/dates, the flight card (airline name via
      `flight_options.AIRLINE_NAMES` fallback logic already stamped in
      `details`, PT-labeled clocks, rounded price, cabin/duration when
      present), then one line per build-out item that exists at send time.
    - `build_repair_email(trip, items, details, refund_line) -> (subject,
      html, text)` — the rebooked flight's facts, the original as a "Was …"
      struck-through line from `details.rebooked_from` (degrading exactly like
      the cascade page when identity is absent), per-leg fixed lines, and the
      refund sentence appended when `refund_line` is not None.
    - Simple inline-styled HTML (one accent color, system fonts), text
      fallback mirrors the HTML line for line. Every field degrades to
      omission, never a crash — builders must work on seed trips and pre-33
      rows.

1.3 Hermetic tests: registry semantics (store/get/clear/normalize/reset);
    builders on a rich trip, a seed trip (no `details`), a repaired trip with
    and without `rebooked_from` and with/without a refund line — asserting
    airline names not codes, "PT" labels, no raw URLs, and that missing data
    omits lines rather than raising.

## 2. Concierge tool + booking-call offer beat

2.1 `email_itinerary_impl(session_id, email_address)` in `concierge.py` (the
    `*_impl` plain-function pattern): resolve the pinned trip via the
    cache-first `ensure_trip_context` path (no pin → speakable no-trip line,
    nothing stored); validate the address with a conservative regex
    (lowercase/strip first) — malformed → speakable re-ask, nothing stored;
    valid → `trip_emails.store`, read trip + items off the loop
    (`asyncio.to_thread`), build the itinerary email, `send_email`, and
    return a speakable line per status: `sent` → confirmation, `disabled` /
    `error` → honest couldn't-send (address stays stored). Never raises.

2.2 Register the eighth tool in `build_agent`
    (`function_tool(..., name_override="email_itinerary")`).

2.3 `BASE_INSTRUCTIONS` gains the offer-beat clause: after a successful
    booking, offer **once** — "Would you like me to send this to your
    email?"; on interest, collect the address, convert spoken forms to a
    standard address ("at" → @, "dot" → .), read it back, and call the tool
    only after an explicit yes; a decline or unclear answer drops the subject
    — never guess, never re-pitch, never read the address back as a URL.

2.4 Hermetic tests: unpinned session line; malformed address re-ask (nothing
    stored); confirmed valid address stores + calls `send_email` with the
    expected to/subject (monkeypatched); `disabled` and `error` statuses
    speak honestly and still store; a repository failure returns a speakable
    string (never raises); purity — no `_SESSION_FLIGHT_OPTIONS`, no
    `_LATEST_SEARCH`, no booking writes from the email path.

## 3. Repair-callback offer + email watcher (`demo.py`)

3.1 `_call_back_with_results`: look up `trip_emails.get(trip_id)` before
    placing Call 2. Address on file → append the one offer sentence to the
    purpose and capture Call 2's session key from the `place_call` payload
    (`room_name`, `call_id` fallback — the disrupt-path extraction). No
    address → today's behavior byte-identical (no sentence, no watcher).

3.2 Email watcher (new background task, `_WATCHER_TASKS` strong-ref set):
    reuse `_await_call_transcript` on Call 2's key; classify the traveler's
    answer to the email offer with a minimal Agents SDK call (the
    `consent.classify_consent` pattern and model env var, email-offer
    prompt); unambiguous yes → build the repair email from the same
    `trip / items / details / refund_line` values already loaded for the
    purpose and `send_email` to the stored address. No / ambiguous / timeout /
    empty transcript / classifier failure → no email. Never raises; log-only
    failures (a broken email path must never affect Call 2 or the cascade).

3.3 Hermetic tests (mocked `vb_cli`, monkeypatched classifier + `send_email`,
    shrunk poll constants — the consent-watcher test pattern): no-address
    path is byte-identical (purpose unchanged, no watcher task); yes sends to
    the stored address with the refund line when present; no/ambiguous/
    timeout send nothing; a `place_call` failure still sends nothing and
    logs; watcher exceptions never propagate.

## 4. Suite, docs, deploy

4.1 Full containerized suite green: `docker compose exec backend pytest`.

4.2 README operator run-sheet: one short addition to "Running it live" — the
    booking-call email beat (speak a real address, confirm it back) and the
    Call 2 offer (answer plainly); note the operator-Gmail check mirrors the
    Phase 39 smoke.

4.3 PR from `vb/feature/agent-email-offers` into `vb/dev` (push trigger
    deploys); run evidence (pytest output, deployed walkthrough) recorded in
    this spec dir per the standing convention — not the PR body.
