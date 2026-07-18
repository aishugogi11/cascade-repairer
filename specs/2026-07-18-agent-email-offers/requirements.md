# Requirements — Phase 40: Agent email offers

The conversational surface on top of Phase 39's send module (`email_client.py`,
QA-closed 2026-07-18 — domain Verified, deployed test send landed in Gmail from
`Cascade <info@talktomytrip.com>`): the agent offers email on both demo calls,
captures the address by voice on the booking call, and reuses it on the repair
callback.

## Scope

**In scope (full roadmap scope, settled at the spec interview):**

1. **Booking-call offer beat** (the web-orb Concierge conversation, not a phone
   call): after a successful booking the agent offers once — "Would you like me
   to send this to your email?" On a yes it collects the address by voice,
   reads it back, and only after an explicit confirmation calls a new Concierge
   tool that stores the address for the trip and sends the **itinerary email**.
2. **Repair-callback offer beat** (Call 2, the outbound results callback in
   `demo.py::_call_back_with_results`): when an address is on file for the
   trip, Call 2's purpose gains one offer sentence ("Would you like an email of
   this?"). A background watcher reads Call 2's transcript (the consent-watcher
   pattern) and, on an unambiguous yes, sends the **repair email** to the
   stored address. No re-ask of the address — it's on file. When **no address
   is on file** (traveler declined or never booked by voice), Call 2 carries no
   offer sentence and no watcher runs — byte-identical to today's Call 2.
3. **Email address stored per trip ID, in memory** (interview decision): a
   small module-level registry keyed by `trip_id` (the `consent.py` precedent),
   protected by the service-level single-instance cap. Lost on redeploy —
   accepted at demo scale. The TODO's transcript re-parse fallback is **not**
   built.
4. **Email content** mirrors what the agent speaks:
   - *Itinerary email*: the booked trip — flight with rich fields (airline
     name, cabin, duration, PT clock labels, rounded price) plus whatever
     build-out items exist at send time.
   - *Repair email*: the repair summary consistent with Call 2 — the rebooked
     flight's identity and facts, the original flight as a struck-through /
     "was" line from `details.rebooked_from`, per-leg fixed statuses, and the
     **PayPal refund sentence when one fired** (the same `_maybe_refund_line`
     output Call 2 speaks).

**Out of scope:**

- Any persistent storage of email addresses (BigQuery column, new table) or
  transcript re-parsing.
- Address capture on phone calls (Call 1 or Call 2) — the voice-capture path
  is the web Concierge conversation only.
- Inbound email, reply handling, or any send not triggered by a spoken yes.
- New dependencies — `httpx` (transport) and the Agents SDK (classifier) are
  already pinned; Resend is already the deliverability path.
- Retry machinery for failed sends (the PayPal `pending` precedent — honesty
  rides on the provider at demo scale).

### Data shape

| Piece | Shape |
|---|---|
| Registry | `trip_id -> email address` (module-level dict, in-process) |
| Itinerary email | subject + simple HTML (+ text fallback) built from `Trip` + `ItineraryItem` rows at send time |
| Repair email | subject + simple HTML (+ text) built from the same `trip / items / details / refund_line` data `build_results_purpose` consumes |
| Send result | `email_client.send_email` status dict — `sent` / `disabled` / `error`, never raises |

## Decisions

1. **In-memory registry, new module `backend/api/trip_emails.py`** (interview:
   "In-memory only"). Mirrors `consent.py`: module state + tiny store/get/clear
   functions, importable by both `concierge.py` and `demo.py` without circular
   imports. No repository writes — the Phase 32 wholesale-`details` write-back
   contract is untouched.
2. **Strict voice confirmation before storing or sending** (roadmap: the
   demo's known STT hazard). The confirmation contract lives in
   `BASE_INSTRUCTIONS`: the agent must read the captured address back and get
   an explicit yes before calling the tool; a decline or ambiguous answer
   means **no tool call, nothing stored, nothing sent — never a guessed
   address**. The tool itself is the backstop: it validates the address with a
   conservative pattern and returns a speakable re-ask on anything malformed
   (model adherence is instructions; validity is code — the Phase 34
   precedent).
3. **Store on confirmed valid address, speak the send status honestly.** The
   tool stores the address first (the repair email can still use it later),
   then sends; `sent` gets a confirmation sentence, `disabled`/`error` gets an
   honest "I couldn't send it just now" — the tool never claims an email
   arrived when the module said otherwise, and never raises (speakable-string
   standing rule).
4. **Call 2 yes/no rides the existing watcher machinery.** `place_call`'s
   returned payload already carries the `room_name` session key (Phase 31);
   `_await_call_transcript` is reused as-is, and the yes/no classification
   follows `consent.classify_consent`'s minimal Agents SDK pattern
   (`CONSENT_LLM_MODEL`, default `gpt-5.4-mini`) with an email-offer prompt.
   Timeout, ambiguity, classifier failure, or an empty transcript all mean
   **no email** — the same honesty posture as consent.
5. **Offer beats are scripted lines woven into existing prompts, accepting
   the known gpt-5.4-mini adherence looseness** (interview: no instruction
   tuning today beyond the added clauses; the Phase 34 close-out precedent —
   stochastic conversational contracts are not asserted in tests).
6. **Simple branded HTML** (interview decision): inline styles only, from
   `Cascade <info@talktomytrip.com>` via `send_email`, content readable as
   text — not the rich-template investment, not bare plain text.

## Context

- **Event day is today (2026-07-18).** Ship the smallest faithful version;
  every failure path degrades to "no email," never a broken call or a dead
  voice turn.
- **Tone**: email copy mirrors the spoken register — airline *names* never
  codes, PT-labeled clocks, rounded prices, short sentences. Subjects are
  plain ("Your trip to Los Angeles" / "Your trip is fixed"). No URLs the
  Concierge wouldn't speak; `info@talktomytrip.com` is outbound-only, so no
  "reply to this email" copy.
- **Stack pointers**: `email_client.send_email` (guarded transport — never
  raises, `RESEND_API_KEY` kill switch keeps the suite hermetic);
  `concierge.py` tool pattern (`*_impl` plain functions + `function_tool`
  registration in `build_agent`, speakable failures); `demo.py`
  `_call_back_with_results` / `_watch_consent_then_repair` (background
  watcher, strong task refs, never raises); `call_purposes.py` (pure purpose
  builders); `flight_options.AIRLINE_NAMES` and the `details` /
  `rebooked_from` stamp (email facts come from the same data the pages and
  Call 2 read).
- **Blocking-call rule**: repository reads for email content go through
  `asyncio.to_thread`; `send_email` is already async httpx.
- **Quota**: the booking-call beat costs zero calls (web voice); the repair
  beat rides Call 2, which the demo run already places — Phase 40 adds no
  outbound calls.
- **Validation must not require PR-body evidence** (retired DoD-B, 2026-07-16
  evening replan) — run evidence lives in this spec dir and the changelog.
