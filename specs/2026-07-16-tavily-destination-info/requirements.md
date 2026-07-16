# Requirements — Phase 35: Tavily destination-info tool for the Concierge

Branch: `vb/feature/tavily-destination-info` (off `vb/dev`). Spec settled with
Josh at the 2026-07-16 feature-spec interview (all three recommended options
chosen: one tool only; always-register with speakable fallback; subtle offer +
mocked tests).

## Scope

One new trip-aware, read-only Concierge tool that answers "what's happening
there / things to do during my trip" with live Tavily results during the call.

**In scope**

| Piece | Shape |
|---|---|
| Tool | `destination_info(question: str)` registered on `build_agent` alongside the existing five tools, closing over `session_id` like the others |
| Impl | `destination_info_impl(session_id, question)` in `backend/api/concierge.py` — reads the pinned trip via `ensure_trip_context` (cache-first, no new BigQuery read after the first turn) and appends the trip's destination(s) and dates to the query **server-side** before searching |
| Search | Tavily `search` with `include_answer=True`, `search_depth="basic"`, small `max_results` (3) — condensed for voice; prefer the `answer` field, fall back to joined result snippets, cap the returned string length |
| Result | Always a **speakable string** (standing house rule) — plain sentences, no URLs, no markdown |
| Instructions | One added `BASE_INSTRUCTIONS` sentence: answer destination questions (things to do, what's happening, local recommendations) with the tool **when asked** — no proactive pitch after booking |
| Dependency | `tavily-python` added to `backend/requirements.txt` (approved — it is the phase's stated deployment surface) |
| Deployment | `TAVILY_API_KEY` set on Cloud Run via `--update-env-vars` merge (survives redeploys, same as `OPENAI_API_KEY`) — the one piece code alone can't ship |

**Not in scope**

- No real hotel/dining/experience booking — those APIs aren't coming;
  `complete_trip`'s mocked build-out stays exactly as-is (settled with Josh,
  recorded in the roadmap TODO).
- No second tool (weather / dining recs). The interview settled **one tool
  only** — the stretch tool is out of the spec entirely; every extra tool is
  another mid-demo model choice.
- No changes to the trip model, booking writes, repair cascade, consent flow,
  session pinning, or any page. Blast radius: `concierge.py`, one deps line,
  tests.
- No persistence of search results — nothing enters `_SESSION_FLIGHT_OPTIONS`,
  `_LATEST_SEARCH`, session snapshots, or BigQuery.

## Decisions

1. **Always register, speakable fallback** (interview). The tool is on the
   agent unconditionally. A missing `TAVILY_API_KEY`, an import failure, a
   Tavily API error, or a timeout all return a short speakable apology
   ("I couldn't look that up just now — ask me again in a moment.") from
   inside the tool body's try/except. Never an exception out of the tool,
   never a startup failure.
2. **Blocking client off the event loop.** `TavilyClient.search` is
   synchronous — it MUST run via `asyncio.to_thread` (the standing
   concurrency_core rule: blocking calls inside async paths would stall the
   very conversation this keeps alive). Wrap in `asyncio.wait_for` with a
   modest timeout (~8 s) so a slow search degrades to the speakable fallback
   instead of a dead-air voice turn.
3. **Lazy client, env read at call time.** No module-import-time key read and
   no module-level client construction that needs credentials — importing
   `concierge.py` (and therefore running the hermetic suite) must require no
   `TAVILY_API_KEY`, matching the GCP-helpers convention.
4. **Unpinned session degrades gracefully.** With no pinned trip the tool
   searches the traveler's question as-is (no trip garnish, no error) — the
   agent naturally includes the place being asked about.
5. **Deliberate divergences from the proof notebook**
   (`jupyter_notebook/agent_search.ipynb`): `search_depth="basic"` not
   `"advanced"` (advanced can take seconds inside a live voice turn),
   `include_answer=True` (the notebook returns raw result dicts), integer
   `max_results`, and no `pydantic.BaseModel.model_config` mutation (a
   notebook-only hack — do not port).
6. **Subtle offer** (interview): the agent answers destination questions when
   asked; it does not proactively pitch the ability after booking.
7. **Mocked tests only in the bare suite** (interview): Tavily is mocked at
   the client boundary; no live-network test rides in CI or bare local runs.
   A live spot-check is a manual validation step, not a new pytest marker.

## Context

- **Tone:** replies are spoken aloud — the tool returns condensed plain
  sentences the agent can relay in one or two conversational sentences. No
  URLs, no markdown, no list formatting in the returned string. Follow the
  existing speakable-failure copy style ("I couldn't…", "I don't see…").
- **Pattern to follow:** the five existing tools in `build_agent`
  (`backend/api/concierge.py`) — an async `_destination_info` closure wrapped
  with `function_tool(..., name_override="destination_info")`, delegating to a
  module-level `destination_info_impl` that tests call directly.
- **Proof of concept:** `jupyter_notebook/agent_search.ipynb` — a working
  Agents SDK agent with a `tavily_search` function tool, same SDK/model/
  pattern as the Concierge (with the divergences in Decision 5).
- **Stack limits:** OpenAI Agents SDK pinned per `requirements.txt` comments;
  tests hermetic (no network, no credentials); pytest runs inside the
  container via `docker compose exec`.
- **Validation style:** per the 2026-07-16 evening replan, `validation.md`
  must not require PR-body evidence — run evidence lives in this spec
  directory and the changelog entry.
