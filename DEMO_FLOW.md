# Demo Flow

Demo Code Flow (url: https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/cascade)

1. The initial booking conversation is a real tool-calling LLM agent, not pre-staged data. Every utterance you speak flows: Vocal Bridge → the /query seam (web_call.py) → answer_query() in concierge.py, which builds an OpenAI Agents SDK agent (gpt-5.4-mini by default) fresh for that turn and runs it with up to 6 internal turns. The agent carries seven live function tools (concierge.py). Booking is reflected on the webpage.

   **The return-question beat (Phase 34, optional after booking):** once the outbound is booked, ask the orb *"is there a way to get home?"*. The agent asks for your return date (suggesting the trip's end date), then `check_return_flights` derives the reverse route from the booked trip and asks **Tavily web search** — speaking an indication like "I can't book the return from here, but there are nonstop flights back that day on Delta, American, and JetBlue." This is deliberately **verify-only**: web schedule info, never searched fares — nothing appears on the page's candidates panel and nothing becomes bookable (the Tavily path stores no options, unlike `search_flights`). Saying "whenever" instead of a date gets a general route indication. Spec: [`specs/2026-07-16-return-flight-indication/`](specs/2026-07-16-return-flight-indication/).
2. Press **Cancel flight → cascade**. The browser disables the button and sends `POST /v1/demo/disrupt` with the trip currently pinned on the page. The handler in [`demo.py`](backend/api/demo.py) then:

   - Loads the real trip and its itinerary items. This both validates that the trip has a flight and gives Call 1 an accurate route, date, and list of downstream reservations.
   - Builds the disruption/consent script with `build_disrupt_purpose()` in [`call_purposes.py`](backend/api/call_purposes.py).
   - Queues Call 1 through Vocal Bridge **before changing any trip data**. If the call cannot be queued, the endpoint returns an error and the flight remains unchanged.
   - Calls `break_trip_flight()`, which updates the flight's BigQuery `itinerary_items` row from `booked` to `broken`.
   - Registers an `awaiting_consent` record for this trip and starts `_watch_consent_then_repair()` as a background task. No repair starts from the button click itself.

   The dashboard keeps polling while this happens. On its next poll it turns red, shows the broken flight, and says that Cascade is waiting for the traveler's go-ahead. The 60-second repair timer is intentionally not running yet.

3. Vocal Bridge places **Call 1** to the phone number configured in `VOCAL_BRIDGE_CALLEE_PHONE`. `place_call()` in [`vb_cli.py`](backend/api/vb_cli.py) pins the configured caller agent, injects the trip-specific purpose into its prompt, and runs the Vocal Bridge CLI call. The caller tells the traveler which real flight was cancelled, explains that nothing has been changed yet, and asks one clear question: should Cascade rebook the flight and recheck the rest of the trip?

   Vocal Bridge returns both a `call_id` and a `room_name`. The backend stores the `room_name` as the join key because completed Vocal Bridge session logs contain the room name, not the outbound call ID. Only these sanitized identifiers and the call status reach the API response; the phone number and API key do not.

4. The traveler answers **yes** or **no** during Call 1. After the call completes, `_await_call_transcript()` polls the Vocal Bridge session logs every four seconds, for up to three minutes, until that room has both a `completed` status and a non-empty transcript. `classify_consent()` in [`consent.py`](backend/api/consent.py) gives the transcript to a one-turn OpenAI Agents SDK classifier (`gpt-5.4-mini` by default), which returns only `yes`, `no`, or `ambiguous`.

   | Answer/result | Backend state | Repairs | Call 2 |
   |---|---|---|---|
   | Clear yes, such as "yes", "sure", or "go ahead" | `granted` | Started | Attempted after the repairs settle |
   | Clear no | `declined` | Not started | No |
   | Unclear answer or classifier failure | `declined` with a retry message | Not started | No |
   | No completed transcript within three minutes | `timed_out` | Not started | No |

   A declined, unclear, failed, or timed-out decision leaves the flight broken, shows the stand-down message on the dashboard, and re-enables the Cancel button for a retry. The safe default is always to make no repair or rebooking changes without a clear yes.

5. **Yes, a successful yes-path produces a second Vocal Bridge call.** First, the watcher atomically changes consent to `granted` and calls `launch_trip_repairs()` in [`sabre_tools.py`](backend/api/sabre_tools.py). That creates one `asyncio` task per itinerary item, so the flight, hotel, ground transport, dining, and experience repairs run concurrently rather than one after another.

   Each task follows the same lifecycle in [`concurrency_core.py`](backend/api/concurrency_core.py): set its item to `repairing`, run the category repair tool, then set it to `fixed`. The flight tool re-shops the route and date with Sabre InstaFlights, excludes the cancelled flight when the data permits, chooses the closest replacement arrival, and records a new booking. Sabre shopping can be real; the PNR write remains deliberately mocked because the hackathon credentials cannot create a real booking. The other trip legs are rechecked or repaired by their current Sabre/mock adapters.

   `_call_back_with_results()` waits for all of those tasks to settle, reloads the actual post-repair trip and latest booking details, and builds Call 2 with `build_results_purpose()`. **Call 2 is the results callback**: it names the selected replacement flight, speaks the fare difference when available, and confirms which downstream reservations were rechecked. If a repair is still unresolved, the callback script is built to say that honestly instead of claiming everything is fixed. A full yes-path therefore uses two outbound calls; a no-path uses only Call 1.

6. The fixes are reflected on the dashboard through polling, not a push connection. Every 1.5 seconds, [`page.html`](backend/api/assets/cascade/page.html) requests `GET /v1/itinerary/status/{trip_id}`. The endpoint in [`itinerary_ui.py`](backend/api/itinerary_ui.py) reads the trip and item rows from BigQuery, adds the latest booking-derived detail for each item, and includes the current consent state.

   As the five repair tasks write `broken → repairing → fixed`, the browser diffs each poll against the previous one. That drives the card animations, repair activity feed, disruption score, and recovery timer. The timer starts only when the first `repairing` status is observed after consent and freezes when no item remains `broken` or `repairing`.

   **Phase 32 (shipped 2026-07-16):** `_rebook_flight()` now writes the replacement flight's timestamps, fare, currency, and identity onto the flight's `itinerary_items` row before the `fixed` transition — a failed write raises, so the card can never flip `fixed` over stale fields. When the flight card reaches `fixed` it shows the **rebooked** flight's time and price, with the original preserved as a struck-through "Was …" line (the additive `detail.rebooked_from` field, derived from the repair booking; it degrades to clock-and-price when the original flight had no stamped identity). The re-stamped identity also means a second disruption excludes the flight the traveler is actually on. Spec: [`specs/2026-07-16-repaired-flight-on-page/`](specs/2026-07-16-repaired-flight-on-page/).

The successful state sequence is:

`booked → broken + awaiting_consent → granted → repairing (five parallel tasks) → fixed → results callback`
