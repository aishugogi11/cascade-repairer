# BACKLOG 

**Replanned 2026-07-06** around the team's locked demo concept, the **Cascade Repairer** (see `mission.md`): a booked trip takes a live flight cancellation and the agent repairs all five legs in parallel *while still talking*. That decision added the concurrency spike (Phase 5), repair-capable Sabre tools (Phase 6), and the live itinerary UI (Phase 10), and demoted the real-time voice-to-voice port to a stretch goal. **Updated 2026-07-06 post-Phase-3:** promoted the Vocal Bridge live-call test page from `TODO.md` to Phase 4, front of the line per Josh; later phases renumbered (old 4–11 → 5–12). **Updated 2026-07-07 post-Phase-5:** the concurrency question is answered — no rewire needed; the pattern (`backend/api/concurrency_core.py`) is standing infrastructure for Phases 7–9. Two Phase 5 loose ends folded into Phase 6: surfacing failed status writes, and proving real BigQuery rows flip with fresh `updated_at`. **Updated 2026-07-08:** Phase 7 now also carries the L4 "Voice as a Tool" outbound-call pattern, because it is not otherwise covered by an active phase; the stretch L4 item remains only the full real-time voice-to-voice architecture port. **TODO triage 2026-07-08 (post-Phase-6):** the Discord 2026-07-07 "agent reaches out first" demo opening is noted in Phase 12 (mechanics live in Phase 7); the LandingAI email-scanning ideas were dropped per Josh — the thread stays in README as context. **Updated 2026-07-09 post-Phase-10:** the live itinerary UI shipped and is QA-verified on Cloud Run; its residual visual edge cases (backend-restart recovery, cancelled-item rendering, projector readability) are carried into the Phase 12 rehearsal checklist below. **TODO triage 2026-07-09 (post-Phase-10):** the Phase 7 outbound-call persistence idea is promoted to Phase 13, deliberately after the rehearsal. **Updated 2026-07-10 post-Phase-12:** the dress rehearsal is QA-complete — the two-button demo page ran the full cascade on Cloud Run with real outbound calls, all five repairs in ~21 s (see changelog) — so the foundation is done and Phase 13 is unblocked. **TODO triage 2026-07-10 (replan):** the Phase 11 eval triage in `TODO.md` was audited against the code — D1, the openai 2.44.0 pin, the deployed eval re-run, and the "don't archive Phase 11" guard were already done and are dropped; the web-call silent-on-connect incident is irrelevant to the demo (it runs on outbound calls, not the web-call page) and moves to the backlog. Per Josh: **demo polish runs first** (demo-day risk beats plumbing), so Phase 14 below jumps the queue ahead of Phase 13 — phase numbers are historical, the file order is the execution order. **TODO triage 2026-07-11:** the "Talk to My Trip" iOS app is promoted to roadmap Phases 16–17 and jumps ahead of everything here — App Store first-review latency (days) makes an approvable submitted build the immediate goal; Phases 14 → 13 → 15 now wait behind it. The same TODO's web-demo-polish idea is backlogged below. **TODO triage 2026-07-12 (post-Phase-18):** the two validation-pass hotfixes (timezone discipline, iOS voice pin for the displayed trip) are promoted to roadmap **Phase 19**; the `complete_trip` build-out visibility gap is backlogged below — revisit after Phase 17's device QA, and pull it forward if rehearsals keep hitting the "is it done yet?" stall. **TODO triage 2026-07-12 (replan, post-Phase-19):** the TEMP mobile_voice latest-trip bridge removal is backlogged as **Phase 20** below per Josh — it cannot start until App Review approves the submitted binary, and event day runs on the current binary + backend either way. **App Review replan 2026-07-16:** v1.0 (3)'s Guideline 3.2 rejection moved the approval trigger to roadmap Phase 36's same-build Unlisted App Distribution recovery. **TODO triage 2026-07-13:** the Sabre keys arrived — the CERT exploration is promoted to roadmap **Phase 25**, ahead of the dashboard (Phases 22–23) per Phase 24's time-gate; the deal-manufacturing post-booking upsell engine is backlogged below per Josh — revisit after Phase 23, must not put the July 18 core at risk, and the minimum demoable slice if promoted is `extend_stay` only.

## Phase 14: Demo polish — stage feel and visual edge cases (runs FIRST)

- **`repair_delay_seconds` knob on `POST /v1/demo/disrupt`** (default ~15 s, tunable from the runbook): place the call and break the flight immediately, but launch the repairs from a background task that sleeps first — so the flight lingers red while the phone rings and the agent says "give me thirty seconds," instead of the screen healing before the bad news lands. Recovery becomes ~15 s + ~21 s ≈ 36 s, still well under the 60-second gate.
  > **TODO (Josh's live stage run, 2026-07-10):** "When I click 'Flight Cancelled', it actually reverts it immediately before I even get the phone call saying that my flight has been cancelled." The repairs (~21 s) beat the telephony (~10–15 s to ring + answer + opening line); the story plays backwards.
- Close the two never-verified itinerary-page edge cases (parked from Phase 10, descoped from the Phase 12 branch): **backend-restart mid-poll recovery** and **a cancelled item rendering muted** (the CSS exists on both pages but has never been exercised with a real cancelled row).

## Phase 13: Outbound call persistence

Post-rehearsal per Josh (TODO triage 2026-07-09): the demo works without a local call record; this lands only once the Phase 12 run is clean. One small phase: `outbound_calls` table + repository (same config-driven pattern as the six existing tables), a row written at dial time, and backfill of the Vocal Bridge session id / recording URI when `/status` / `/recording` resolve them. Consider echoing turn transcripts into `turns` so the eval harness (Phase 11) can score phone calls like web sessions.

> **TODO (from Phase 7 manual QA, 2026-07-08):** Persist outbound calls in our own DB.
> Today the L4 outbound-call flow keeps no local record: `POST /call` returns a
> Vocal Bridge `call_id`, the session log lives only in Vocal Bridge (`vb logs`),
> and the two ids aren't linked anywhere on our side (learner confusion proved it:
> call_id was naturally pasted into `/status?session_id=`). Idea: an
> `outbound_calls` table (call_id, purpose, name, placed_at, vb_session_id,
> call_status, recording_gcs_uri) written at dial time and back-filled with the
> session id/recording when `/status` / `/recording` resolve them — schema yaml +
> config.yaml metadata entry + repository, same pattern as the six existing
> tables. Natural home: fold into Phase 9 (the Concierge places calls and the
> Phase 12 opening beat needs the call on record) or a small standalone phase.
> Consider also echoing turn transcripts into `turns` so eval (Phase 11) can
> score phone calls like web sessions.

**Update 2026-07-10 (replan):** this phase also closes eval decision **D4** — the MOS leg needs a completed Vocal Bridge session id, and `outbound_calls` rows supply them durably. (Interim recipe, usable today: place a demo call, then read the session id from `GET /v1/outbound_call/status` — the Phase 12 rehearsal calls already produced valid completed sessions.)

> **TODO (eval-harness triage, 2026-07-09, D4):** Where should a validator obtain/record the completed Vocal Bridge session id the MOS leg needs? (Criterion went UNTESTABLE because none was available.) Option B: wait for Phase 13 (`outbound_calls` persistence) to supply ids from our own DB. → DECISION (2026-07-10): fold into Phase 13.
> **Carried QA item:** MOS leg end-to-end: run the harness with `--vb-session <id>` from a real completed Vocal Bridge call → `mos_estimate` 1.0–5.0 persisted with judge notes. Only remaining open QA item for Phase 11.

## Phase 15: Eval harness hardening

Make eval results trustworthy enough to gate on: settle the three open Phase 11 decisions, encode them as tests, and eval-capture one full rehearsal run so event-day metrics have a baseline. Audited 2026-07-10: all three are confirmed still open in the code (`ArchitectureResult.failed` ignores latency-less runs; CLI exits 0 on partial failure; neither guarding test exists).

- Decide and implement **D2** (WER-only runs), **D3** (per-surface latency bands), **D5** (CLI exit codes) — decision texts preserved verbatim below.
- Add the three missing tests: `test_failed_turn_error_appears_in_row_notes`, `test_partial_architecture_run_without_latency_is_failure`, and an exit-code test per D5.
- Run `make eval` (Cloud Run job for persisted rows) alongside one full two-beat demo run and record the baseline in the Phase 12 runbook's timings table.

> **TODO (eval-harness triage, 2026-07-09, D2):** Should a cascaded run with a successful WER leg but zero successful `/converse` turns count as a result row? Today `ArchitectureResult.failed` is false if WER exists, which let the deployed dry-run print cascaded rows with `ttfb_ms` NULL while the latency leg was actually broken. Option A: WER-only run is a failure (require ≥1 successful latency turn). Option B: keep WER-only rows valid.
> **TODO (D3):** What latency bounds count as "plausible" per surface? `validation.md` step 1 expects hundreds-to-low-thousands of ms; the passing local-fallback run measured 4–19 s per turn. Option A: accept and document per-surface ranges (local slower; deployed must meet the demo budget). Option B: treat >low-thousands ms anywhere as a failure.
> **TODO (D5):** What should the CLI exit code mean when *some* runs fail? Today any surviving row → exit 0, which masked the deployed concierge breakage in a dry-run and could allow partial non-dry persistence. Option A: non-zero (or a distinct code, e.g. 3) when any architecture × scenario failed. Option B: keep exit 0 if anything succeeded.
> **TODO (implementation task):** Add `test_failed_turn_error_appears_in_row_notes` — build a row from a result with one failed turn, assert `notes.turns[*].error` carries it — file: `backend/tests/test_eval_harness.py`.

## Phase 20: v1.0.1 post-approval update — remove the TEMP latest-trip bridge

**Trigger: a future decision to reopen iOS distribution** *(re-armed 2026-07-18: the original
trigger — App Review approving v1.0 (3) through the Phase 36 unlisted recovery — is gone; the
Apple path was dropped unshipped that morning, see the roadmap drop note and tech-stack § iOS
app; v1.0 (3) history: submitted 2026-07-11, rejected 2026-07-16 under Guideline 3.2)*. One
small phase, one release, only if distribution is ever reopened:
bump the app to v1.0.1 (the native `vbSetTrip` wiring is already merged — Phase 19), archive →
upload → release per `IOS_DEPLOY.md` (historical runbook), then delete the backend bridge block
and its page tests in the same phase. Until this ships, the known accepted gap stands: any
older binary's voice session pins the backend's globally newest trip, not a user-scoped one
(direct Xcode installs carry the current `vbSetTrip` build, so the gap only bites stale
installs).

> **TODO (Phase 19, 2026-07-12):** Remove the mobile_voice page's TEMP latest-trip bridge:
> the page self-fetches `/v1/sabre_tools/latest_trip_id` as its lowest-precedence `trip_id`
> so the in-review binary is trip-aware from a backend deploy alone. Remove once native
> `vbSetTrip` ships in v1.0.1 (the first post-approval App Store update) — the block is
> marked `TEMP bridge` in `backend/api/mobile_voice.py`, with page tests in
> `tests/test_mobile_voice.py` to drop alongside it.

## Deal manufacturing: post-booking upsell engine (backlogged 2026-07-13 — not yet a phase)

Backlogged at the 2026-07-13 triage per Josh: revisit **after Phase 23** (the dashboard is the
anchor demo and this must not put the July 18 core at risk); if promoted, the minimum demoable
slice is **`extend_stay` only** (one kind, one sweep, one offer). Its one external dependency —
whether the hackathon CERT keys include the Flight Search API v1 — is answered by roadmap
Phase 25 (Sabre CERT exploration). The full TODO writeup is preserved verbatim below.

> **TODO (verbatim, 2026-07-13):**
>
> **Pitch line:** *Sabre gives you inventory; our agent manufactures the deal.* Sabre has no
> self-serve pre-packaged-deals endpoint (verified 2026-07-13: the inspirational/intelligence
> suite — Destination Finder, InstaFlights, Top Destinations, Low Fare Forecast, Travel
> Seasonality — lives under the retired `/docs/rest_apis/...` scheme; the current primitive is
> the cache-based **Flight Search API v1**, `developer.sabre.com/rest-api/flightsearch-api/v1`,
> open-destination + open-date cheapest-fare search). So the differentiator is building the
> package layer ourselves: background agents assemble bundle candidates from raw Sabre
> inventory, we rank them against the just-booked trip with embeddings, and the voice agent
> offers the top match at the natural moment. Every other team books what the user asked for;
> ours notices the trip could be better and says so, unprompted.
>
> ### Demo moment
>
> Right after `complete_trip`, while the four build-out cards are still materializing on the
> 1.5 s pollers, the agent volunteers: *"One thing before you go — you land Friday at 10 a.m.
> and fly out Saturday night. Staying through Sunday actually saves you $102: the hotel drops
> $40 a night and the Sunday return is $62 cheaper. Want me to extend it?"* A "yes" runs the
> extension (hotel date change + flight rebook — both already exist as repair tools); the
> cards flip on screen while the agent confirms.
>
> ### How it works — three parts
>
> 1. **Background deal-hunter agent (reuse `concurrency_core`).** When `book_flight` /
>    `complete_trip` lands, fire an un-awaited `asyncio.create_task` (never a sequential
>    await — the conversation must keep flowing) that sweeps for bundles around the booked
>    trip: adjacent-date flight prices (±1–2 days on the return via Flight Search API if the
>    keys are entitled, plain Bargain Finder Max re-searches if not), adjacent-date hotel
>    rates (`/v5/get/hotelavail` across the extension window), and nearby-experience fills for
>    free days. In `SABRE_MODE=mock`, the mock client returns deterministic sweep results so
>    the whole feature works offline and in CI (per-call dispatcher fallback already handles
>    `real` failures). Completions report into the per-session event log so the session
>    snapshot can answer "found anything?" by name.
>
> 2. **Deals corpus in BigQuery.** New `deal_candidates` table (repository-layer module +
>    `config.yaml` metadata entry + `create_vocal_bridge_tables.sh`, the donor pattern):
>    `deal_id, trip_id, kind (extend_stay/cheaper_return/experience_fill/hotel_upgrade),
>    summary (speakable one-liner), price_delta, currency, components (JSON — the concrete
>    legs/rates to book if accepted), embedding (ARRAY<FLOAT64>), created_at, expires_at,
>    status (proposed/offered/accepted/declined/expired)`. Writes are query-job DML like
>    everything else. `expires_at` is mandatory — this is the `_LATEST_SEARCH` staleness
>    lesson (Phase 21 validation) applied from day one.
>
> 3. **Embedding rank + voice offer.** Embed a textual profile of the booked trip
>    (route, dates, hotel, stated preferences pulled from the session's turns) and each
>    candidate's summary with OpenAI embeddings; cosine in-process in Python — **no vector
>    DB, no pgvector** (3–10 candidates per trip; a helper in `concierge.py` is plenty, and
>    tests mock the embedding call at the helper boundary to stay hermetic). Top candidate
>    above a similarity floor becomes (a) a line in the agent's session snapshot marked
>    authoritative — so the Concierge offers it in its own voice after `complete_trip`
>    instead of being tool-triggered — and (b) an additive, best-effort `deal_offer` block
>    on `GET /v1/itinerary/status/{trip_id}` (the `detail` / `pending_options` precedent:
>    omitted when there's nothing to say, a failed read can never break the poll) so the
>    booking page / dashboard candidates panel renders it on the "AI Recommended" card
>    treatment. An `accept_deal(deal_id)` tool books the components via the existing repair
>    tools and flips the row to `accepted`; every failure path returns a speakable string.
>
> ### Existing seams this rides on (no new infra)
>
> - `concurrency_core.py` — background task + event log + session snapshot (proven Phase 5/6).
> - `book_flight_impl` / `complete_trip` in `concierge.py` — the trigger points.
> - Repair tools (`repair_tools.py`) — hotel date change + flight cancel/create already
>   compose the "extend it" action.
> - Status-endpoint additive-payload pattern (`detail`, `pending_options`) — `deal_offer`
>   is the third instance of the same contract.
> - Booking page right-column candidates panel (Phase 21) — the visual slot already exists.
> - BigQuery repository layer + config-driven table ids — one new table, donor pattern.
>
> ### Standing rules that apply
>
> - DB stores UTC; every spoken/displayed time is Pacific, labeled "PT".
> - Blocking work (embedding HTTP call, BigQuery DML) inside async paths goes through
>   `asyncio.to_thread` / stays off the event loop.
> - Tool and failure-path returns are speakable strings; prices rounded, no airline codes.
> - Tests hermetic: no `OPENAI_API_KEY`, no GCP creds — mock at helper boundaries.
> - Additive status-payload blocks are best-effort and can never break the poll.
>
> ### Open questions for the triage interview
>
> - **Flight Search API entitlement** — ask the Sabre team today (2026-07-13, keys expected)
>   whether the hackathon CERT keys include it; if not, the BFM + hotelavail sweep is the
>   plan of record and Flight Search API is a nice-to-have swap.
> - **Sequencing vs. Phases 22–23 (dashboard):** this is a booking-beat feature; the cascade
>   dashboard is the anchor demo. Propose slotting after Phase 23 unless the dashboard
>   finishes early — it must not put the July 18 core at risk. Cutting scope to
>   `extend_stay` only (one kind, one sweep, one offer) is the minimum demoable slice.
> - Does the offer also belong in the iOS `RecommendationSheet` (it already reads `detail`),
>   or is web-only enough for event day?
> - Embedding model choice + where the trip-profile text is assembled (concierge vs. a
>   dedicated helper) — implementation detail, decide in the feature spec.
>
> ### Chains with (separate, later idea — not part of this item)
>
> The same sweep machinery pointed at *pre-disruption* gives **speculative repair**: pre-warm
> per-leg alternatives at booking time so the cascade's recovery timer collapses from ~35 s
> to single digits ("Plan B was already booked before the flight canceled"). Park it as its
> own inbox item once the deal engine exists — shared corpus table, shared sweeps, different
> trigger.

*(Triage-interview answers, 2026-07-13: sequencing → after Phase 23; scope if promoted →
`extend_stay` slice only. The remaining open questions — iOS `RecommendationSheet` inclusion,
embedding model, trip-profile assembly point — stay open for the eventual feature spec.)*

## Backlog (post-event unless it bites)

- **Voice agent can't see the `complete_trip` build-out** (TODO triage 2026-07-12, post-Phase-18
  validation; revisit after Phase 17's device QA — pull forward if rehearsals keep hitting it):
  after `complete_trip`, "is the rest of my trip ready?" hedges forever. Two causes: the
  build-out (`_build_out_trip`, `backend/api/concierge.py`) never reports into the per-session
  event log the way `fix_trip` repairs do, so the LIVE STATUS snapshot never says "done" (and
  TRIP CONTEXT deliberately excludes statuses); and the build-out takes ~64 s live (two BigQuery
  DML jobs per item) versus the spoken promise of "the next few seconds" — hermetic tests mock
  the writes, so it never showed. Proposed fix matches the existing pattern: report each item
  through `core.start_background_call` so the snapshot reads "hotel: done, dining: pending…",
  and soften the spoken copy. Demo stakes: judges will ask "is it done?" over voice; today the
  agent can only stall while the screen shows completion.
  > **TODO (Josh, live `/v1/web_call/` rehearsal on deployed `c897f15`, 2026-07-12):** booking
  > worked end to end (flight booked, all five items landed `booked`, `all_clear: true`), but
  > after `complete_trip` the traveler asked "is the rest ready?" repeatedly and the agent
  > hedged "still being put together" for the whole conversation — even after the build-out had
  > finished. Observed: the final turn named all five parts (the re-pin had landed) but still
  > wouldn't commit to "finalized."
- **Web demo polish to the mockup** (TODO triage 2026-07-11): bring the `/v1/itinerary/` page up to `about/ui_ideas/ui_mockup_2026_07_09.png` — Josh: the current page "is a solid start" but "needs to be polished and end up like" the mockup. Deprioritized behind the iOS app (roadmap Phases 16–17); overlaps Phase 14's stage-feel polish, so fold in there if Phase 14 runs before this surfaces on its own.
- **Coroutine warnings in the repair-failure test path** — confirmed still real 2026-07-10: `tests/test_sabre_tools.py::test_repair_trip_failed_write_surfaces_as_error_event` emits `RuntimeWarning: coroutine '_rebook_flight' was never awaited` at `concurrency_core.py:89`. Diagnose before scheduling any fix; could mask future async failures.
- **Revisit the `openai==2.44.0` pin** when an `openai-agents` release supports openai 2.45+ (pinned 2026-07-09 after the transitive break that killed every deployed agent turn; `openai-agents==0.17.7` verified affected through 0.18.0).
- **Web-call page Greeting + Debug Mode** (VB dashboard config, from the 2026-07-09 silent-on-connect incident): the agent is configured to wait for the user to speak, which reads as broken. Irrelevant while the demo runs on outbound calls (per Josh 2026-07-10); do it only if the web-call page returns as a demo or team surface.

## Stretch (post-rehearsal, only if time allows)

- **Real-time voice-to-voice architecture (L4 port)** — demoted 2026-07-06: the demo runs on the Concierge hybrid, so the L4 port is off the critical path. Notebook mastery still counts toward the mission's skill goal.
- Mocked extras from the team thread (Google Maps distances, Uber, Costco Travel bundles) — only after the core repair loop is clean end to end.

---

**Event day (July 18):** flip the Sabre config flag to real credentials (mocks remain the runtime fallback), assemble the Cascade Repairer demo with the team on top of the completed foundation ([changelog.md](changelog.md) — Phases 1–12 all shipped), and polish the 60-second moment. Outbound-call budget: 10/day on the Developer plan, resetting 00:00 UTC (5 PM PDT the evening before) — 2 calls per full run-through, so bank at least 4 for the real demo.
