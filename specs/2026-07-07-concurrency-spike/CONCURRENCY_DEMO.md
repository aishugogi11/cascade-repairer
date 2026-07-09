# Concurrency Demo — 60-Second Screen Share Script

A QuickTime screen recording, run entirely from the FastAPI Swagger page, that
shows the team Pallavi's flag is solved: **the agent answers while a
10-second call and five parallel repairs are all still running.**

Revised after the 2026-07-07 dry run — the narration below leads with the
story, names the 10-second test explicitly, and translates the JSON instead
of reading it.

## Before you record

1. **Use a deployment that has the session-snapshot change** (the agent
   answering "how are the repairs coming?" by naming them). If the PR hasn't
   merged and redeployed yet, the deployed agent will answer vaguely — record
   against local instead:
   - Cloud Run: `https://vocal-bridge-be-dev-24105435206.us-west1.run.app/docs`
   - Local: `http://localhost:1019/docs` (`make backend` first)
2. **Warm it up** — hit `/v1/hello/hello_world` once so a Cloud Run cold start
   doesn't eat your minute.
3. **Open two browser tabs of the same Swagger page** (no scrolling between
   endpoints mid-recording):
   - **Tab 1:** expand `POST /v1/concurrency_spike/cascade` → *Try it out* →
     paste the cascade payload below.
   - **Tab 2:** expand `POST /v1/concurrency_spike/talk_while_tool_runs` →
     *Try it out* → paste the talk payload below.
4. **Fresh `session_id` in both tabs, changed every take** (`take-1`,
   `take-2`, …). Reusing a session accumulates old slow calls and repairs,
   and the agent will truthfully — confusingly — mention "a previous slow API
   call." One take, one session.
5. QuickTime → File → New Screen Recording → select the browser window.

### Tab 1 payload — `POST /cascade`

```json
{
  "session_id": "take-1",
  "wait": false
}
```

### Tab 2 payload — `POST /talk_while_tool_runs`

```json
{
  "session_id": "take-1",
  "question": "How are the repairs coming along?",
  "slow_seconds": 10
}
```

Same `session_id` in both — that's what makes the follow-up aware of the
cascade.

## The recording (~50 seconds)

Narration is written to be spoken, not read off the screen. Never read JSON
keys aloud — say what they mean, and point the cursor at the field.

| Time | Do | Say |
|------|----|----|
| 0:00–0:08 | Tab 1, payload visible. | "Quick proof of the thing we were worried about — the agent going quiet while it repairs a broken trip. A traveler's flight just got cancelled, and that breaks all five bookings. Watch." |
| 0:08–0:15 | Click **Execute** in Tab 1. Cursor on `pending_tasks`. | "Back instantly — flight, hotel, ground transport, dining, experience: all five repairing right now, in parallel." |
| 0:15–0:22 | Switch to Tab 2. Cursor on `slow_seconds: 10`, then **Execute**. | "Now, while all of that runs — plus a ten-second API call I'm starting at this same moment — I ask the agent: how are the repairs coming?" |
| 0:22–0:30 | **Say nothing while it thinks.** The pause is the test playing out — it's tension, not dead air. | — |
| 0:30–0:45 | Cursor moves in order: ① `followup_answer` ② `followup_latency_seconds` ③ `answered_before_tool_finished: true` ④ `slow_call.state: "running"`. | "There it is. It answered in about six seconds, named everything it's working on — and here's the actual acceptance test: answered-before-tool-finished, true. The ten-second call is still running. It never went quiet." |
| 0:45–0:52 | Re-click **Execute** in Tab 2. Cursor on `completed_events`. | "Ask again a few seconds later — the repairs are landing one by one, reporting back in while the conversation keeps going. That's the concurrency question closed." |

## Wording traps from the dry run

- **Name the 10-second call.** The acceptance criterion is *"the agent
  answers while a 10-second fake API call is still running"* — if the
  narration never mentions it, the video proves the wrong, weaker thing.
- **"Ask again," not "refresh."** You're re-executing a request, not
  reloading a page.
- **Don't read durations off the wrong field.** Repairs are deliberately
  staggered 2–6 seconds (that's what makes the overlap visible) — they are
  not all 2 seconds.
- **"Mock calls" or "simulated calls," not "simulated mock calls."**
- Skip the phrase "starter infrastructure" — lead with the traveler's broken
  trip, not the deployment.

## Pass criteria to point at on screen

- `answered_before_tool_finished: true` — Pallavi's test, verbatim.
- `followup_latency_seconds` < 10 while `slow_call.state` is `"running"`.
- `pending_tasks` showing the five repairs + `slow_api_call` concurrently.
- The `followup_answer` text naming the in-flight repairs (session awareness).

## If a take goes sideways

- Timing is forgiving: repairs take ~8–15s on Cloud Run (2–6s fakes + BigQuery
  writes), so you have that window after Executing Tab 1 to fire Tab 2 and
  still catch everything pending. If `pending_tasks` comes back short, you
  waited too long — completions just show in `completed_events` instead, which
  still reads fine on camera.
- The follow-up answer wording varies per run (it's a live LLM); any answer
  that names the repairs is a pass.
- Flub a line → new `session_id`, re-record. Takes are cheap; a clean single
  take beats an edited one for team trust.
