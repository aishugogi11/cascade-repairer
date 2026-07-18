# Validation — Phase 40: Agent email offers

Per the 2026-07-16 evening replan: run evidence lives in this spec directory
and the changelog entry — **no PR-body evidence is required or checked**.

## Automated

`docker compose exec backend pytest` — the full bare suite green (hermetic: no
`RESEND_API_KEY`, no `OPENAI_API_KEY`, no GCP credentials), including new
tests asserting at minimum:

1. **Registry** (`trip_emails`): store/get round-trips per trip_id; addresses
   normalized (strip + lowercase); `clear` removes; `get` on an unknown trip
   returns None; `_reset` empties state between tests.
2. **Content builders** (`email_content`): itinerary and repair emails build
   from a rich Phase-33 trip, a seed trip (no `details`), and a repaired trip
   with and without `rebooked_from` / refund line — airline **names** never
   codes, clocks labeled "PT", rounded prices, the "Was …" line present
   exactly when `rebooked_from` has something to say, the refund sentence
   appended only when passed, missing fields omitting lines rather than
   raising, and both HTML and text variants non-empty.
3. **Concierge tool** (`email_itinerary_impl`): unpinned session → speakable
   no-trip line, nothing stored; malformed address → speakable re-ask,
   nothing stored; confirmed valid address → stored **and** `send_email`
   called with that address and the itinerary subject; `disabled` and `error`
   send statuses → honest couldn't-send line, address still stored, no raise;
   a repository read failure → speakable string, no raise.
4. **Email-path purity**: the tool and the watcher leave
   `_SESSION_FLIGHT_OPTIONS`, `_LATEST_SEARCH`, consent state, and the
   repositories' booking/item writes untouched (the Phase 34 purity-test
   precedent) — nothing bookable enters a session from the email path.
5. **Call 2 offer + watcher** (mocked `vb_cli`, monkeypatched classifier and
   `send_email`, shrunk poll constants): no address on file → Call 2 purpose
   byte-identical to today and no watcher spawned; address on file → purpose
   carries exactly one offer sentence; classified **yes** → one send to the
   stored address, repair content, refund line included when the run had one;
   **no**, **ambiguous**, transcript **timeout**, and classifier failure →
   zero sends; watcher exceptions are swallowed and logged, never propagated;
   Call 2 is placed regardless of any email-path failure.
6. **Never-raise transport contract holds**: no new code path lets an email
   failure surface as an exception into a voice turn, Call 2 placement, or
   the cascade (asserted via the monkeypatched `send_email` returning
   `error`).

## Manual (deployed service — the demo path)

1. **Yes path, booking beat** (web orb, zero call quota): book a trip by
   voice on `/v1/cascade/`; when offered, say yes and speak a real operator
   address; the agent reads it back; confirm — the itinerary email arrives in
   the operator's Gmail from `Cascade <info@talktomytrip.com>` with the
   booked flight's airline name, PT times, and price matching the page.
2. **Yes path, repair beat** (one full demo run — 2 calls): break the trip,
   grant consent on Call 1; when Call 2 offers the email, say yes — the
   repair email arrives at the same address, showing the rebooked flight, the
   struck-through original, and (when the rebooking was cheaper) the PayPal
   refund sentence Call 2 spoke.
3. **Decline path** (no quota — booking beat only): on a fresh trip, decline
   the email offer — the conversation moves on, nothing is sent, and a
   subsequent repair run's Call 2 carries no email offer sentence.
4. **Ambiguity guard**: give a garbled/partial address once — the agent
   re-asks rather than confirming a guess; nothing arrives.
5. **Edge**: ask for the email with no trip booked in the session — the
   agent speaks the no-trip line; nothing sent.

Accepted looseness (standing, Phase 34 precedent): the exact offer wording
and the read-back phrasing are model behavior — manual checks assert the
*outcomes* (stored/sent/not sent), not verbatim lines.

## Tone check

- Both emails read in the spoken register: airline names, "PT"-labeled
  clocks, rounded prices, short sentences; no airline codes, no fare-class
  letters, no raw URLs, no "reply to this email" copy.
- Subjects are plain and specific (e.g. "Your trip to Los Angeles",
  "Your trip is fixed").
- The agent's offer is a subtle single ask — never re-pitched after a
  decline (the `destination_info` instruction precedent).

## Definition of done

- All automated assertions above pass in the containerized suite.
- Manual walkthroughs 1–3 pass on the **deployed** service: spoken yes →
  email arrives; spoken no → nothing sent, nothing stored beyond the decline
  (the roadmap's completion line).
- README run-sheet updated; run evidence (pytest output + dated deployed
  walkthrough notes) recorded in this spec directory.
- Merged to `vb/dev` via PR and deployed by the push trigger.
