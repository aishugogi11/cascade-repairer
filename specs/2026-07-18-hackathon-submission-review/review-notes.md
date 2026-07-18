# Review notes — version 1 of the hackathon submission (2026-07-18)

Reviewed against: `specs/tech-stack.md`, `specs/changelog.md`, `README.md`
(§ Course integration patterns), `backend/api/concierge.py`, the submitted
video's transcript (preserved in the Phase 42 roadmap entry), and a fresh
suite run on this branch.

## Verdict

**Version 1 is effective but not submittable as-is.** The story, structure
(IDEA / IMPLEMENTATION / HOW WE USED VB / HOW WE USED SABRE / ROADMAP), and
energetic register are right and were kept. What blocked as-is submission:
a literal `<insert pattern here (1, 2, or 3)>` placeholder, ~10 typos and
garbled phrases, a stale six-tool list, an unverified test count, two
overstatements a probing judge could catch, and trailing numbered notes that
duplicated the main prose. All fixed in `IMPLEMENTATION_DETAILS.md`; the
final text is a corrected edit of v1, not a rewrite.

## Fact verification (plan group 1)

- **Test count**: v1 said "570+ tests" (the PR #71-era number). Fresh run on
  this branch, freshly built image: **634 passed**, 12 skipped
  (environment-dependent), 11 deselected (the fenced live-CERT tests). The
  text now says 634.
- **Tool list**: v1 listed six tools. `concierge.py` registers **eight**:
  `fix_trip`, `search_flights`, `book_flight`, `complete_trip`,
  `trip_status`, `destination_info`, `check_return_flights`,
  `email_itinerary` (`concierge.py:1146-1157`). The text now names all eight.
- **Integration pattern** (the placeholder): per README § Course integration
  patterns — the booking orb is **Pattern 2** (voice for an existing agent:
  VB delegates via `useAIAgent → /v1/web_call/query` to the Concierge), and
  the two outbound calls use the **Pattern 3** capability (voice as a tool),
  triggered by the demo orchestrator. The text states both plainly without
  course-numbering jargon.
- **State sequence**: v1's `booked → broken + awaiting_consent → granted →
  repairing ×5 → fixed → results callback` matches the shipped lifecycle;
  folded into the IMPLEMENTATION stack sentence.

## Corrections by section

**IDEA** — kept nearly verbatim (it's the strongest section). One fix: "the
hotel is rechecked against the new flight" overstated a mock — replaced with
the parallel-repair framing that doesn't claim a real hotel recheck.
"Rebooked on live Sabre inventory" tightened to "re-shopped on live Sabre
inventory" with the different-flight guarantee attached (the shopping *is*
live; the write isn't, and that split is handled in the Sabre section).

**IMPLEMENTATION** — typos fixed ("reservaration", "rebbooking" in spirit);
tool list corrected to eight and the email spell-back beat added (it's in
the video — a judge-verifiable moment); the mock nature of the four
non-flight repair legs stated plainly ("as simulated services"); test count
634; the state sequence, domain email, and Docker/GCP posture folded in
from v1's trailing notes; the different-flight exclusion and closest-time
pick folded in from note 3.

**HOW WE USED VOCAL BRIDGE** — kept; the placeholder resolved here as the
two-pattern sentence (existing-agent delegation for the orb, voice-as-a-tool
outbound calls); "keeps answering questions while repairs run" kept — it's
true (`trip_status` mid-repair) and demo-verifiable.

**HOW WE USED SABRE** — the decided precise-but-confident framing: shopping
and re-shopping live (InstaFlights on CERT, real priced itineraries), PNR
writes simulated because `createBooking` isn't entitled on the hackathon
CERT credentials, framed as a credentials swap away from real booking. Also
added Phase 41's one-option-per-airline presentation (shipped today; it's
what makes the spoken menu a genuine choice).

**ROADMAP** — kept with light cleanup; "the remaining trip legs" sharpened
to "real inventory for the remaining trip legs" (consistent with the
simulated-services honesty above).

**Trailing numbered notes (v1 items 1–3 + stray lines)** — dropped as a
block; every load-bearing fact (tools, ConsentClassifier, state sequence,
exclusion/closest-time/price-delta, email working, domain, deployment)
was folded into the main sections. The paste-ready text is one coherent
piece for the single form field.

**Not published**: the `?code=` access parameter (deliberately absent from
the submission text).

## Submission field: Vocal Bridge call session ID (verified 2026-07-18)

The form also requires a VB call session ID (assistant-placed, ≥15s, with a
recording). Verified via `vb logs list` in the container (caller agent
pinned) — the two newest sessions are the submitted video's run, transcripts
matching the video verbatim:

- **Submitted: `83ce8523-b676-4925-9637-3408b1927500`** — Call 2, the results
  callback (2026-07-18 20:11 UTC, outbound, 34 s, completed; recording
  confirmed downloadable via `vb logs download`, 391 KB MP3). Speaks the
  JetBlue rebooking, the $80 PayPal refund, and the email offer.
- Alternate: `b5ab30a0-85e9-4418-a259-0de52e7f69fc` — Call 1, the consent
  call (20:10 UTC, outbound, 38 s, completed).

## Typos and garble fixed

reservaration, Conceirage, iteratry, altnative, communciates, asycio,
concurrecy, intergration, rebbooking, "transtript" (TODO text itself),
"Booking is show on webpage", inconsistent "re shops / re shopping"
hyphenation.
