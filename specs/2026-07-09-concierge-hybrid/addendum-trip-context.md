# Addendum — Trip context in the Concierge (post-QA, 2026-07-09)

**Why:** The Phase 9 live QA (transcript in `validation.md`) passed the roadmap
acceptance, but exposed two conversation-level gaps: the agent could fix a trip
it couldn't describe ("what place are you trying to fix if you don't even know
my itinerary?"), and it promised completion notifications it cannot deliver
(delegation is pull-based). Trip Q&A was deliberately out of Phase 9 scope
(interview decision); Josh approved adding a lightweight version now rather
than waiting for Phase 12, so every rehearsal call before event day runs the
real conversation. Branch: `vb/feature/trip-context`.

**What:**

1. **Session-pinned trip context** (`concierge.ensure_trip_context`): the trip
   is resolved once per session (most recently created trip by default) and its
   static facts cached in process — title, origin → destinations, dates, item
   types/locations — then injected into every turn's instructions as an
   authoritative `TRIP CONTEXT` block (the measured Phase 5 wording rule).
   - Statuses are deliberately absent from the summary: live repair progress
     stays with the in-memory snapshot. No BigQuery read on any turn after the
     pin — the foreground stays fast.
   - Pinning also means a mid-call `seed_trip` cannot switch the agent's trip,
     and `fix_trip` reuses the pinned items (no second read).
   - A failed resolution never blocks the turn and is never cached — the next
     turn retries; meanwhile the agent is told no trip is on file.
2. **The Phase 12 seam**: `ensure_trip_context(session_id, trip_id=...)` pins an
   explicit trip — the disruption/outbound-call opening beat knows exactly which
   trip broke and will pass it instead of relying on latest-trip.
3. **No false promises** (`BASE_INSTRUCTIONS`): the agent cannot notify
   proactively, so it now invites "ask me again in a moment" instead of
   promising "I'll let you know."

**Validation delta (automated, hermetic):** trip summary present in the turn
instructions (facts, no statuses); pin happens exactly once per session;
a failed pin doesn't fail the turn and retries next turn; explicit `trip_id`
pin works without the latest-trip query; existing Phase 9 suite unchanged.
Manual: repeat the QA call — "where do I fly into?" should be answered from the
trip, and no notification promises should be made.
