# Requirements — Concierge hybrid architecture (Phase 9)

## What this phase proves

**The demo architecture.** The Phase 5 acceptance test, now over voice: the
foreground agent holds a live voice conversation while all five real repair tools
(Phase 6, BigQuery writes) execute in parallel in the background. You speak "my
flight was cancelled — fix my trip"; the agent fires the cascade and keeps
talking; "how are the repairs coming?" gets a grounded, by-name answer while rows
flip broken → repairing → fixed in BigQuery.

## The hybrid shape (what exists, what's new)

The foreground/background split already has three working layers; Phase 9 wires
them together:

- **VB voice layer** (Phase 8): AI-Agent-mode agent owns STT/TTS/turn-taking,
  speaks bridge lines, polls `check_agent_response` — observed working in the
  Phase 8 QA transcript. **Unchanged this phase** (no re-provisioning).
- **`/query` seam** (Phase 8): `web_call.answer_query(session_name, query)` —
  built to be swapped. This phase swaps it.
- **Concurrency pattern** (Phase 5, `concurrency_core.py`): background tasks +
  per-session event log + per-turn session snapshot. `sabre_tools.repair_trip`
  already assembles the real-repair cascade over it. **The Concierge lifts that
  assembly, not a reimplementation.**

New: a **Concierge foreground agent** behind the seam — fast model, per-turn
build with the session snapshot in its instructions (the Phase 5 finding: snapshot
wording must be marked authoritative or the model asks clarifying questions), and
one tool that **launches** the trip repairs in the background and returns
immediately. The VB session name is the concurrency session id, so snapshot and
event log tie to the voice session.

## Scope

### In scope

| Piece | Behaviour |
| --- | --- |
| `backend/api/concierge.py` | `answer_query(session_name, query)` — the new seam implementation: per-turn foreground `Agent` (model `CONCIERGE_LLM_MODEL`, default `gpt-4.1-mini`) with multi-turn history, session snapshot in instructions, and the repair-launch tool |
| Repair-launch tool | `fix_trip` function_tool: resolves the trip (latest trip, the `sabre_tools.latest_trip_id` lookup), launches all item repairs via `concurrency_core.run_repairs` with the real `_repair_call` wiring, returns immediately naming what was launched — **never awaits the repairs** |
| Shared launch seam | The `calls`/`specs`/`do_repair` assembly inside `sabre_tools.repair_trip` extracted to a reusable `launch_trip_repairs(...)` used by both the endpoint and the Concierge tool (endpoint behaviour unchanged) |
| Seam swap | `web_call.answer_query` delegates to `concierge.answer_query`; `/v1/web_call/` page, token mint, and turn logging unchanged |
| Single-writer cleanup | Roadmap-mandated (folded from Phase 6): the five repair tools stop stamping `fixed`; `_repair_one` (cascade unit) becomes the **only** writer of itinerary status transitions. Tools keep writing their `bookings` rows. |

### Out of scope

- The outbound-call tool on the Concierge (`make_phone_call`) — Phase 12's opening
  beat wires it; the tool already exists (Phase 7).
- General itinerary Q&A from BigQuery (what's booked, when, where) — the agent
  answers about *repairs* from the snapshot; broader trip reads are not this phase.
- The live itinerary UI (Phase 10), evaluation harness (Phase 11).
- VB-side changes: agent re-provisioning, endpointing, interruption engineering —
  VB owns those; our latency lever is returning `/query` fast.
- A feature flag / second surface — the swap is direct, per the user's decision.

## Decisions

- **Swap the `/query` seam** (user decision): one surface; the existing
  `/v1/web_call/` page just gets smarter. The seam stays a plain function, so
  tests (and any rollback) are one import away.
- **Foreground must answer fast** (user's top constraint): fast model, tool
  returns at launch (the `concurrency_agent._start_slow_api_lookup` inversion),
  no inline `await` of repair work anywhere on the turn path. Target: `/query`
  responds within the Phase 5 measured window (~2–6 s) while five repairs run.
- **Real repairs, real rows** (user decision): the Phase 6 tools against the
  seeded trip — the walkthrough's BigQuery evidence (fresh `updated_at`, status
  lifecycle) is the acceptance evidence here too, now concurrent with speech.
- **Trip resolution = latest trip**: the demo flow (seed → break → call) has one
  active trip; the tool resolves it server-side rather than asking the traveler
  for an id. A voice conversation must never require a UUID.
- **Session id = VB session name**: `answer_query` already receives it; using it
  as the `concurrency_core` session id makes the snapshot per-call and lets a
  reconnect start clean.
- **Single-writer cleanup stays in** despite not being ranked in the interview:
  it is written into the Phase 9 roadmap entry ("Cleanup folded in from Phase 6").
  Consequence to accept: tools invoked *outside* the cascade unit no longer flip
  item status — status transitions are owned by `_repair_one` alone.
- **Per-turn agent build** (Phase 5 finding): the snapshot goes in `instructions`
  at build time, marked authoritative, so "how are the repairs coming?" is
  answered by name, never with a clarifying question.

## Context

- **Patterns to follow**: `concurrency_agent.py` (snapshot wording, tool-launches-
  and-returns inversion, per-turn build), `sabre_tools.repair_trip` (the launch
  assembly being lifted), `web_call.py` (seam signature, history dict, hermetic
  test style), `hello.py` (plain functions kept callable for tests).
- **Standing rules**: BigQuery DML through `asyncio.to_thread`; in-process
  session/event registry is deliberate (single Cloud Run instance).
- **Tests stay hermetic**: no `OPENAI_API_KEY`, no GCP credentials — mock
  `Runner`, repositories, and the launch seam at their boundaries.
- **Tone**: spoken replies one–two short conversational sentences (the
  `cascade_core` instruction style); no markdown, no stage directions. The
  launch confirmation should sound like triage, not a job scheduler ("I'm
  rebooking your flight and fixing the other four now — ask me anything
  meanwhile").
- **No new dependencies.**
