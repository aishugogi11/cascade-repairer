# Vocal Bridge Training Changelog

Completed roadmap phases, compressed to title, completion date, and outcome. Full
task-level detail lives in each phase's spec directory (linked where one exists) and in
git history. Open and upcoming work stays in [roadmap.md](roadmap.md).

Ordered newest phase first.

---

## Phase 29 — Real repair data: the cascade re-shops InstaFlights
**Completed:** 2026-07-15 (implementation complete, manual QA pending; merged PR #51 with remediation PR #52; independent validation returned **FAIL** on the acceptance package [DoD-B] only — every automated and safely runnable live criterion passed, but PRs #51/#52 carry placeholder descriptions instead of the required pre-merge mock/CERT snippets and the mock-mode BigQuery walkthrough was untestable on local creds; report in the spec dir) · **Spec:** [specs/2026-07-15-real-repair-data/](2026-07-15-real-repair-data/)

The demo's credibility pivot: when the flight breaks, the repair now speaks real replacement flights instead of a mock swap. `_rebook_flight` re-shops the broken flight's route and date through the Phase 27 `instaflights_search` dispatcher op (replacing the content-empty BFM `flight_search`), picks a real alternative — a different flight number/time than the cancelled one where possible — and carries it plus the alternatives into the booking row's `raw_response` so the booking page's `detail` panel shows real price-delta / why-chosen data; `FlightOption`, `_parse_instaflights_options`, and the spoken-option helpers were extracted verbatim into a new cycle-free `backend/api/flight_options.py` and re-exported through `concierge` so every existing caller resolves unchanged. PNR writes stay on the mock client (permanent entitlement posture, guarded by a regression test); both credentialed CERT checks report `pnr_write: mock client` and the bare suite is green (405 passed).

## Phase 30 — Search-hardening close-out: Phase 28 validation gaps
**Completed:** 2026-07-15 (implementation + hermetic suite green, merged PR #47 and deployed on `vb/dev`; independent validation returned **FAIL** on two non-code items only, both re-verified as environmental rather than implementation defects — an empty PR #47 description [DoD-B], and a live CERT priced-search test hardcoding DFW→LAX +30d that drifted to empty; report in the spec dir) · **Spec:** [specs/2026-07-15-search-hardening-closeout/](2026-07-15-search-hardening-closeout/)

The four Phase 28 remediation items shipped on one branch (PR #47) so Phase 29 starts from validated ground: `search_flights_impl` now clears both `_SESSION_FLIGHT_OPTIONS` and its owned `_LATEST_SEARCH` slot on every non-optioned return (missing input, unsupported market, error, no-results) so a traveler told "no flights" can't book a stale choice; a six-case parametrized test asserts `NYC→JFK`/`WAS→IAD`/`CHI→ORD` alias in both request positions and reach the market check; a POST-path test proves `_post` refreshes the token once on a 401 and raises on a second; and `git_pull_dev.sh` defaults its base branch to `vb/dev` ahead of the `gh`/`origin/HEAD` fallbacks (which resolve to `main` and `--admin`-merge immediately). Bare suite 387 passed; the two FAILs were independently confirmed non-code — the CERT test's DFW→LAX +30d is honest-empty cache drift while JFK→LAX +30d returns real fares through the identical path, and the empty-PR-body gap is superseded by the `pr-evidence-guard` workflow (PR #48) that auto-populates future descriptions.

## Phase 28 — Search hardening: Phase 27 validation fixes and honest empties
**Completed:** 2026-07-14 (implementation + deployed real-mode spot checks the same evening; independent validation returned **FAIL** on acceptance-package gaps — every behavior criterion passed, but criterion 6's six metro-alias cases and the POST-path 401 test are uncommitted and the pre-merge PR-evidence rule was missed; remediation plus two report-surfaced risks are roadmap **Phase 30**, report in the spec dir) · **Spec:** [specs/2026-07-14-search-hardening/](2026-07-14-search-hardening/)

All seven hardening items shipped on one branch (PR #45, Cloud Build `f56451bd`, evidence in the PR body) and the guided-search path came out honest, deduplicated, and drift-resistant ahead of Phase 29: the parser skips any itinerary touching an unmapped airport (connections included) and dedupes identical options before numbering, the mock speaks airport-local times so mock west-to-east arrivals follow their departures (`end_ts > start_ts` restored), the documented InstaFlights no-results 404 (`WARN.RAF.APPLICATION`, live-probed) returns an honest "couldn't find any flights" instead of a mock swap — verified against the deployed service with zero fallback warnings — 401s clear and refetch the token exactly once, metro codes alias server-side (`NYC→JFK`, `WAS→IAD`, `CHI→ORD`) with a matching instructions clause, and a new cert-fenced parity test surfaced 29 unmapped supported-market codes (the live list carries metro and non-US codes) now added to `AIRPORT_TZ`.

## Phase 27 — Real Sabre search in the demo path
**Completed:** 2026-07-14 (merged PR #43 and verified live on Cloud Run the same day; independent validation returned **FAIL** — both defects fixed by Phase 28 the same evening) · **Spec:** [specs/2026-07-14-real-sabre-search/](2026-07-14-real-sabre-search/)

Judges now hear real airlines, fares, and routes while booking stays mock: `search_flights_impl` shops InstaFlights (`GET /v1/shop/flights`) through the dispatcher with additive response shapes, a static `airport_tz.py` table converting the API's offset-less airport-local times to PT (with an `arrive_date` red-eye guard on booking writes), best-effort supported-markets validation behind a speakable redirect, and `onlineitinerariesonly=N` forced unconditionally — real CERT fares spoken on Cloud Run with `SABRE_MODE=real` the day it merged, while the validator's two behavior defects (endpoint-only unmapped-airport check, mock Pacific-fiction clocks re-read as airport-local) became Phase 28.

## Phase 26 — Validation fixes: close out Phase 25's FAIL
**Completed:** 2026-07-14 (close-out re-validation **PASS** same day, report in the spec dir; one tracked follow-up — the different-day `pytest -m cert` dated artifact — rides with roadmap Phase 24, D4) · **Spec:** [specs/2026-07-14-validation-fixes/](2026-07-14-validation-fixes/)

Every Phase 25 validator failure is closed with tests-and-probes-only changes (PRs #40/#41): the createBooking tripwire now recovers the raw payload from the pydantic `ValidationError`, cancels any harvested PNR unconditionally in `finally`, and asserts the `UNAUTHORIZED_ACCESS` marker explicitly (found live to sit in `type`, not `category` — notes corrected); a hermetic shape-drift suite proves the cleanup guarantee by construction; the CERT sweep grew six executed domain classifications (schedules and car/ground have no REST endpoints, availability and exchange shopping exist but are not entitled, Flight Reshop and EnhancedSeatMap are entitled, and modifyBooking is authorized via a dummy-PNR business error — D2) with nonzero exit codes on network failure and entitlement drift; hard-coded travel dates became computed; and a docs-contract test pins the notes' five decision headings.

## Phase 25 — Sabre CERT exploration: size up what the real keys can do
**Completed:** 2026-07-13 (implementation merged, PR #38; independent validation returned **FAIL** — fixed by Phase 26, whose 2026-07-14 close-out re-validation covered the Phase 25 + 26 criteria and returned **PASS**) · **Spec:** [specs/2026-07-13-sabre-cert-exploration/](2026-07-13-sabre-cert-exploration/)

The hackathon credentials were exercised live against Sabre CERT and the verdict is **real shopping, mock booking**: v2 client-credentials auth verified with a documented env bridge for the Phase 24 flip, Flight Search API v1 entitled and returning real priced itineraries (the deal-engine gate answers **go**), BFM v5 empty on this PCC and `createBooking` entitlement-blocked (`PassengerDetailsRQ` unauthorized — the event-day ask to Sabre staff), a latent dead-`POS`-field bug found in the frozen `shapes.py` — all recorded in `sabre-cert-notes.md` with re-runnable probes and a six-test CERT-marked pytest suite that leaves hermetic CI untouched — while the validator's two failing criteria (a PNR-cleanup guarantee hole in the create tripwire, an incomplete Try-it-Out sweep) plus the different-day re-run remain open in TODO.md behind four pending decisions.

## Phase 21 — Voice booking page: the pre-disruption beat on screen
**Completed:** 2026-07-12 (manual QA passed) · **Spec:** [specs/2026-07-12-voice-booking-page/](2026-07-12-voice-booking-page/)

The booking conversation now has a screen: `GET /v1/booking/` shows the candidates the agent is offering mid-call (via a new additive `pending_options` block on the status poll) and the full five-item reservation as it books, styled to `about/ui_ideas/ui_mockup_2026_07_09.png` — the visual frame Phases 22–23 lift — with the automated suite green (331 passed) and the manual curl-rehearsal walkthrough QA'd 2026-07-12.

## Phase 19 — Validation hotfixes: Pacific-time discipline & pin the displayed trip
**Completed:** 2026-07-12 (QA passed same day; validation report in the spec dir) · **Spec:** [specs/2026-07-12-pacific-time-trip-pin/](2026-07-12-pacific-time-trip-pin/)

Both post-Phase-18 hotfixes shipped together (PR #31, image `be3937a`) and were QA'd live the same day: mock wall-clock times are now declared Pacific at ingest and stored as honest UTC while every user surface renders explicit `America/Los_Angeles` labeled "PT" — the voice-booked 6:15 AM flight that displayed as 1:15 AM now reads 6:15 AM PT for every viewer — and the app's displayed trip pins the voice session through an optional `trip_id` on the `/query` seam (pin-only-if-unpinned, so a just-booked trip is never clobbered), with a TEMP mobile-page latest-trip bridge making the in-review App Store binary trip-aware from a backend deploy alone (removal in v1.0.1 is reminded in TODO.md); one residual rides with Phase 17: real Sabre offset-bearing times still need Pacific conversion when `SABRE_MODE=real` flips.

## Phase 18 — Unpin fresh sessions: make Act 1 guided booking reachable
**Completed:** 2026-07-12 · **Spec:** [specs/2026-07-12-unpin-fresh-sessions/](2026-07-12-unpin-fresh-sessions/)

Act 1 (voice-booking a brand-new trip) is reachable again — deployed 2026-07-12 (PR #29, image `c897f15`) and confirmed by the same-day live web-call rehearsal: the latest-trip auto-pin that shadowed every fresh session with the table's newest trip is gone (`ensure_trip_context` pins only on an explicit `trip_id` or after `book_flight`), today's Pacific date is injected into the agent instructions so relative dates resolve, and a new end-to-end regression test guards the seam that let the bug ship; the documented accepted loss (in-app voice couldn't see a pre-existing displayed trip) surfaced on device the same day and was closed by Phase 19's pin seam.

## Phase 17 — Talk to My Trip: full voice demo experience
**Completed:** 2026-07-12 (shipped & submitted to App Review 2026-07-11; marked complete at the 2026-07-12 evening replan) · **Spec:** [specs/2026-07-11-full-voice-demo/](2026-07-11-full-voice-demo/)

The full voice demo experience shipped and the iOS app made its **first App Store submission** 2026-07-11 (closing the step Phase 16 left open): guided multi-turn voice booking on the Concierge (`search_flights` → `book_flight` → `complete_trip`), the `DEMO_ACCESS_CODE` gate across backend/pages/iOS, the additive `detail` payload + native recommendation sheet, hidden demo gestures, stage-readability polish, the App-Review privacy hardening, and the iOS empty-start onboarding — 290 backend tests green, device-QA'd through the Phase 18/19 hotfixes — with approval treated as a bonus per `mission.md` #4 (web surfaces are the demo path; no new binary until the in-review one is approved, BACKLOG Phase 20) and the surviving residuals (the `SABRE_MODE=real` flip + Pacific conversion of real Sabre offset-bearing times, physical-device QA of the three acts, the `APIConfig.swift` URL review) moved to roadmap Phase 24.

## Phase 16 — Talk to My Trip: App Store submission MVP
**Completed:** 2026-07-11 (implementation + QA; **App Store submission still pending**) · **Spec:** [specs/2026-07-11-talk-to-my-trip-appstore-mvp/](2026-07-11-talk-to-my-trip-appstore-mvp/)

The "Talk to My Trip" iOS app exists and the whole user story works end to end — QA'd 2026-07-11 against the deployed backend (a San Francisco trip voice-booked through the new magic-utterance `book_trip` Concierge tool with the session pin replaced mid-call, five cards materializing on the native SwiftUI timeline, break → heal in 51s with a live mid-repair spoken answer): an Xcode 26 project (iOS 17+, iPhone-only, zero third-party dependencies) whose visible UI is fully native while a hidden 1×1pt WKWebView runs the Vocal Bridge WebRTC client via the new headless `GET /v1/mobile_voice/` page, backed by new `/v1/legal/privacy` + `/v1/legal/support` pages, `PrivacyInfo.xcprivacy`, and in-app break/repair demo controls for App Review — **not yet submitted to the App Store**: the archive → upload → submit step (this phase's original definition of shipped) remains open, and Phase 17 ships as an app update behind that submission.

## Phase 12 — Dress rehearsal: the cascade, end to end
**Completed:** 2026-07-10 · **Spec:** [specs/2026-07-10-dress-rehearsal/](2026-07-10-dress-rehearsal/)

The demo is stage-ready and QA-complete 2026-07-10 (Josh's live projector run plus a curl-driven deployed rehearsal, timings in the spec's `runbook.md`): a two-button operator page (`/v1/demo/`) drives the whole Cascade Repairer story through a new orchestrator router — "Trigger call" places a real Vocal Bridge booking call while the trip seeds server-side, "Flight canceled" places the agent-reaches-out-first cancellation call, breaks the flight, and launches all five parallel repairs — proven on Cloud Run with real phone calls: all five legs fixed in **~21 seconds**, a third of the 60-second gate, with the runbook capturing recovery moves and the ops findings that cost a morning (outbound calling requires the Developer plan — 10 calls/day resetting 00:00 UTC; the DeepLearning.ai partner-grant pool is spent and never refills); known residuals carried to the roadmap: two itinerary-page visual edge cases, eval capture for rehearsal runs, and a stagecraft repair-delay knob so the fix stops beating the bad-news call.

## Phase 11 — Evaluation harness (L5 port)
**Completed:** 2026-07-09 · **Spec:** [specs/2026-07-09-eval-harness/](2026-07-09-eval-harness/)

Voice quality is now measured, not guessed — independent validator PASS 2026-07-09 (report in the spec dir): a CLI harness (`python -m api.eval_harness` / `make eval`) drives the deployed stack per checked-in scenario fixture and persists TTFB/e2e latency, TTS→STT round-trip WER, and a `vb eval`-judged MOS estimate (score nested under `result`, mapped 0–10 → 1–5) to `eval_runs` stamped with git SHA; QA flushed out three real fixes along the way — the unpinned transitive `openai` 2.45.0 break that was killing every deployed agent turn (now pinned 2.44.0), the live `vb eval` report shape, and the stateless-container `--agent` context pin — and persisted runs go credential-free through the `vocal-bridge-eval-harness` Cloud Run job per Josh's no-local-creds decision; latency-plausibility bands (D3) and two harness-hardening decisions (D2/D5) stay open in TODO.md for the Phase 12 rehearsal to consume.

## Phase 10 — Live itinerary UI
**Completed:** 2026-07-09 · **Spec:** [specs/2026-07-09-live-itinerary-ui/](2026-07-09-live-itinerary-ui/)

The demo's second surface is live and QA-verified on Cloud Run 2026-07-09 (Josh's deployed break/repair run plus an independent validator walkthrough, report in the spec dir): `/v1/itinerary/` serves a self-contained mockup-styled page — five status cards, a traveler-voiced repair activity feed, a recovery timer against the 60-second target, and a trip selector — polling a reusable `GET /v1/itinerary/status/{trip_id}` endpoint every 1.5s so the screen flips broken → repairing → fixed while the agent talks; validator-triaged follow-ups were resolved as two added tests (all decisions answered B: no browser-automation dependency), with residual visual edge cases (backend-restart recovery, cancelled-item rendering, projector readability) parked to the Phase 12 rehearsal.

## Phase 9 — Concierge hybrid architecture (demo architecture)
**Completed:** 2026-07-09 · **Spec:** [specs/2026-07-09-concierge-hybrid/](2026-07-09-concierge-hybrid/)

The demo architecture is live and QA-verified on Cloud Run 2026-07-09 (transcript in the spec's `validation.md`): behind the Phase 8 `/query` seam, a fast foreground agent (`concierge.py`) launches all five real repair tools in parallel via the shared `launch_trip_repairs` seam and keeps talking — the live call repaired a broken trip in ~30 seconds while answering "how are the repairs coming?" by name — with `_repair_one` now the single writer of status transitions, and a post-QA addendum (`addendum-trip-context.md`) adding session-pinned trip context (zero per-turn BigQuery reads, explicit `trip_id` as the Phase 12 seam) plus a no-false-promises prompt rule; known residual, by design: the agent only learns a pre-existing `broken` status when told or when repairs launch — Phase 12's agent-calls-first opening covers it.

## Phase 8 — Vocal Bridge web client integration
**Completed:** 2026-07-09 · **Spec:** [specs/2026-07-09-web-client-integration/](2026-07-09-web-client-integration/)

The browser is now a live surface for the backend agent — `/v1/web_call/` serves the L3 "Voice for your Agent" pattern (a VB AI-Agent-mode voice layer delegating every spoken query via `useAIAgent` to a same-origin `/query` seam running an OpenAI Agents SDK agent with per-session memory and `sessions`/`turns` logging) — QA-verified live on Cloud Run 2026-07-09 with a 58-second conversation whose delegated answers, bridge lines, and session close-out all landed; this page is the test surface for Phases 9–12, and the `/query` seam is exactly what Phase 9's Concierge replaces.

## Phase 7 — Course lesson demo routers: cascaded voice + outbound phone tool (L2/L3/L4 ports)
**Completed:** 2026-07-08 · **Spec:** [specs/2026-07-08-course-lesson-demo-routers/](2026-07-08-course-lesson-demo-routers/)

Every course lesson is now a live, lesson-labeled API surface on Cloud Run — the L2/L3 cascaded architecture as `/v1/cascade_demo` (OpenAI STT/LLM/TTS stages plus a full `/converse` with multi-turn memory, `sessions`/`turns` logging, and GCS audio) and the L4 "Voice as a Tool" pattern as `/v1/outbound_call` plus a `make_phone_call` function_tool ready for Phases 9/12 — QA-verified live 2026-07-08 with a real purpose-injected phone call placed, transcribed, and its recording archived to GCS; live QA also flushed out and fixed a latent GCS content-type bug and the real Vocal Bridge session-log shape.

## Phase 6 — Sabre tools: repair-capable, runtime mock fallback
**Completed:** 2026-07-08 · **Spec:** [specs/2026-07-08-sabre-tools/](2026-07-08-sabre-tools/)

The Cascade Repairer has real hands, QA-validated in production 2026-07-08: six OpenAI Agents SDK repair tools (Sabre-documented flight book/rebook and hotel date-shift plus three category mocks) write bookings and status flips through the repositories, behind a Sabre client layer whose shapes trace 1:1 to a live docs pull (`sabre-api-notes.md`) and whose `SABRE_MODE` env flag auto-falls back to the mock per call; the disruption injector (`POST /v1/disruption/break_flight`) triggers the demo on cue, and both Phase 5 gaps are closed — failed status writes now surface as error events, and the deployed walkthrough proved five real BigQuery rows flipping broken → repairing → fixed with fresh `updated_at` in ~35 seconds.

## Phase 5 — Concurrency spike: speak while repairs run
**Completed:** 2026-07-07 · **Spec:** [specs/2026-07-07-concurrency-spike/](2026-07-07-concurrency-spike/)

Pallavi's concurrency flag is answered with measured evidence — no rewire needed: the reusable pattern in `backend/api/concurrency_core.py` (asyncio background tasks + per-session event log + session snapshot in the agent's instructions) let the agent answer a follow-up in ~2–6s live on Cloud Run while a 10-second fake call and five parallel category repairs were all still running, proven hermetically in CI and demoed to the team by video; two carried-over gaps (surfacing failed status writes, proving real row flips) moved into Phase 6.

## Phase 4 — Vocal Bridge live-call test page
**Completed:** 2026-07-06 · **Spec:** [specs/2026-07-06-vocal-bridge-test-page/](2026-07-06-vocal-bridge-test-page/)

The deployed backend now serves a "Testing Vocal Bridge" smoke-test page (`/v1/vb_test/`) that mints session tokens server-side following the L2 lesson call shape and holds a real live voice conversation against the Vocal Bridge API — QA-passed on Cloud Run 2026-07-06, de-risking auth, call shape, and latency before any voice architecture is built on top.

## Phase 3 — BigQuery data layer
**Completed:** 2026-07-06 · **Spec:** [specs/2026-07-06-bigquery-data-layer/](2026-07-06-bigquery-data-layer/)

All six trip/session/eval tables (`trips`, `itinerary_items` with the repair lifecycle, `bookings`, `sessions`, `turns`, `eval_runs`) now exist in `vocal_bridge`, created idempotently by CI on every build from config-driven table ids, with a typed pydantic repository layer over parameterized DML (never streaming inserts, so status flips are immediately updatable) and hermetic mocked-client pytest coverage — QA confirmed via the PR #8 build and BigQuery console.

## Phase 2 — Repo housekeeping & docs
**Completed:** 2026-07-06 · **Spec:** [specs/2026-07-05-repo-housekeeping-docs/](2026-07-05-repo-housekeeping-docs/)

The repo now explains itself to the hackathon team: README rewritten around the mission, stack, and run instructions; `AGENTS.md` trimmed to agent working rules; an OpenAI Agents SDK skill captured from `backend/api/hello.py` patterns; and unused donor dependencies removed from `backend/requirements.txt` — manual QA verified 2026-07-06, with remaining validation-report follow-ups tracked in `TODO.md`.

## Phase 1 — CI/CD pipeline & GCP foundation
**Completed:** 2026-07-05 · **Spec:** [specs/2026-07-05-ci-cd-gcp-foundation/](2026-07-05-ci-cd-gcp-foundation/)

The full deploy loop is live and QA-verified: a GitHub PR into `vb/dev` fires Cloud Build, which builds the container, runs pytest inside it, and deploys `vocal-bridge-be-dev` to Cloud Run in `us-west1` — with the `vocal-bridge-hackathon` project provisioned (service account, Artifact Registry, GCS bucket, BigQuery dataset) and BigQuery/GCS access confirmed from the deployed service via `/v1/hello/gcp_check`.
