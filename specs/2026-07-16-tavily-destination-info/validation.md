# Validation — Phase 35: Tavily destination-info tool for the Concierge

Per the 2026-07-16 evening replan: no PR-body evidence is required — run
evidence (pytest output, live-check transcript) is appended to this spec
directory and the changelog entry.

## Automated

Run inside the container (the shipping artifact):

```
docker compose exec backend pytest
```

Must all hold:

1. **Bare suite green** with zero new warnings and **no `TAVILY_API_KEY`
   set** — the suite stays hermetic (no network, no credentials; mocks at
   the Tavily-client boundary).
2. **Trip-aware query**: with a pinned trip, the query handed to the mocked
   search contains the traveler's question plus the trip's destination(s)
   and dates; with no pinned trip, the question passes through verbatim and
   no error is raised.
3. **Speakable condensing**: a mocked response with an `answer` field returns
   that answer; one without falls back to result snippets; the returned
   string is length-capped and contains no URLs.
4. **Never raises**: missing key, Tavily client exception, timeout, and
   empty-results paths each return the speakable fallback string — asserted
   as a return value, not an exception.
5. **Registration**: `build_agent` includes a tool named `destination_info`
   with no key in the environment (always-register decision).
6. **Off-loop discipline**: the impl reaches the sync Tavily call through
   `asyncio.to_thread` inside `asyncio.wait_for` (assert via the mocked
   seam or source inspection in the test).

## Manual

Rehearsal path is `/v1/web_call/` + the `/query` seam via curl — no outbound
call quota spent. Use a unique `session_name` per check.

1. **Deployed live check (key set on Cloud Run)**: book-free session — ask
   "what's happening in Los Angeles this weekend?"; the reply is one or two
   spoken-style sentences with real, current content, no URLs, no markdown.
2. **Trip-aware check**: pin a trip (book by voice or `?trip_id=`), ask
   "what should I do while I'm there?" — the answer reflects the trip's
   destination without the traveler naming it.
3. **Failure honesty**: with the key absent (local, key unset), the same
   question gets the speakable fallback — the agent apologizes and moves
   on; the session does not stall or error.
4. **Latency feel**: the answer lands within a natural voice pause (basic
   depth + 8 s cap); if it routinely brushes the timeout, tighten
   max_results before considering depth changes.
5. **No leakage**: after a destination question, the booking page's
   `pending_options` and the trip's items are unchanged — the tool wrote
   nothing.

## Tone check

The tool's returned strings and the new `BASE_INSTRUCTIONS` sentence follow
the house voice: short conversational sentences, spoken-aloud friendly, no
URLs/markdown/ids/tool names, failures phrased as a plain apology
("I couldn't look that up just now — ask me again in a moment."). The agent
answers destination questions **when asked** — no proactive pitch after
booking.

## Definition of done

- All automated assertions above pass in the container; suite green and
  hermetic with no `TAVILY_API_KEY`.
- `tavily-python` pinned in `backend/requirements.txt`; image builds.
- `TAVILY_API_KEY` set on `vocal-bridge-be-dev` (survives redeploys via
  `--update-env-vars` merge).
- Manual checks 1–3 pass against the deployed service; evidence (transcript
  snippets, pytest tail) saved in this spec directory.
- Roadmap Phase 35 marked `[x] COMPLETE` at close-out (via the changelog
  flow), leaving order **34 (data-gated) → 24**.
