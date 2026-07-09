# Vocal Bridge Training Changelog

Completed roadmap phases, compressed to title, completion date, and outcome. Full
task-level detail lives in each phase's spec directory (linked where one exists) and in
git history. Open and upcoming work stays in [roadmap.md](roadmap.md).

Ordered newest phase first.

---

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
