# Requirements — Phase 42: Hackathon submission review (IMPLEMENTATION_DETAILS.md)

Roadmap phase: **Phase 42** (`specs/roadmap.md` — the version-1 draft and the
submitted video's transcript are preserved verbatim there, in the phase entry's
collapsed blocks; they are this phase's inputs).

## Scope

**In scope — one deliverable:**

- `IMPLEMENTATION_DETAILS.md` at the repo root: the **final, paste-ready
  submission text** for the hackathon judging form's single Project Description
  field ("IDEA, Implementation details and how you incorporated vocal bridge
  and sabre"). Structured like version 1 (IDEA / IMPLEMENTATION / HOW WE USED
  VOCAL BRIDGE / HOW WE USED SABRE / ROADMAP), corrected and tightened.
- An honest review of version 1 against the shipped system and the video
  transcript, performed as part of drafting. **The review's reasoning lives in
  this spec directory** (`review-notes.md`), *not* in the root file — decided at
  the spec interview: the root file is paste-ready text only.

**Out of scope:**

- No code, prompt, or page changes — this is a documentation-only phase.
- No re-recording or transcript edits; the video is already submitted.
- No new claims about capabilities the demo can't show (nothing speculative
  beyond the ROADMAP section's clearly-future framing).

## Decisions (settled at the spec interview, 2026-07-18)

1. **Root file is paste-ready text only.** No embedded critique, changelog, or
   meta-commentary — a judge-facing artifact Josh copies into the form
   verbatim. Review notes go to `review-notes.md` in this spec dir.
2. **Real-vs-mock honesty: precise but confident.** State it the way the demo
   does: flight **shopping and re-shopping are live Sabre** (InstaFlights /
   Flight Search API v1 on CERT, real priced itineraries); **PNR writes are
   mock** (the credentials' entitlement reality — `createBooking` is
   entitlement-blocked, documented in tech-stack) and the four non-flight
   repair legs are category mocks. Framed as the entitlement reality, not a
   weakness — a judge who probes finds no gap between the text and the system.
   Version-1 claims that overstate ("the hotel is rechecked against the new
   flight", unqualified "rebooked on live Sabre inventory") are corrected.
3. **Tone: punchy, submit fast.** Keep version 1's energetic register and
   roughly its length. Verify every checkable claim; fix errors; don't
   restructure for restructuring's sake. This is an hour of work, not a
   rewrite project.

## Factual corrections the text must carry

From the triage review of version 1 against tech-stack/changelog/README:

| V1 claim | Shipped reality |
|----------|-----------------|
| Six Concierge tools listed | **Eight** tools: `search_flights`, `book_flight`, `complete_trip`, `trip_status`, `destination_info`, `check_return_flights`, `email_itinerary`, plus `fix_trip` (phone-deferral behavior) |
| `<insert pattern here (1, 2, or 3)>` placeholder | The booking orb is **closest to Pattern 2** (voice for an existing agent — VB delegates via `useAIAgent → /v1/web_call/query` to the OpenAI Agents SDK Concierge); the two outbound calls use the **Pattern 3** capability (voice as a tool), operator-triggered — per README § Course integration patterns |
| "570+ tests" | Verify the actual count from the current suite (last known: 572 green at PR #71; re-check on this branch) and state the verified number |
| "the hotel is rechecked against the new flight" | The hotel/ground/dining/experience repairs are **mock category repairs** running in the same parallel cascade; only the flight leg re-shops live Sabre |
| "rebooked on live Sabre inventory" (unqualified) | Re-shopping is live Sabre inventory; the booking write (PNR) is mock — say both |
| Typos/garble: "reservaration", "Conceirage", "iteratry", "altnative", "communciates", "asycio", "concurrecy", "intergration", "rebbooking", "transtript" | Clean copy throughout |
| Trailing numbered-flow notes (items 1–3) duplicating the IMPLEMENTATION prose | Fold anything load-bearing (different-flight guarantee, closest-time pick, price delta, email beats) into the main sections; the paste-ready text is one coherent piece |

## Context

- **The judging form field is one text box** — the file's body must survive a
  straight copy-paste (plain text / minimal markdown; no tables, no collapsed
  blocks, no links other than the live URL).
- **Deadline pressure is real**: submission is today (event day). Bias every
  choice toward shipping.
- Facts source of truth: `specs/tech-stack.md` (§ Backend, § entitlement
  addenda), `specs/changelog.md`, `README.md` (§ Course integration patterns,
  § The one-page demo). The video transcript (roadmap Phase 42 entry) is
  evidence of what the judges saw: booking, email with spell-back, Japanese
  switch, consent call, live repair on screen, results callback with the $80
  PayPal refund, delivered email.
- Live URL in the text: `https://talktomytrip.com/` (the `?code=` param is
  deliberately **not** published in the submission text).
- Team credit: **Team PAJA** — keep as v1 has it.
