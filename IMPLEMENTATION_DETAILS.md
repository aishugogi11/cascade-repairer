# Cascade Repairer — Team PAJA — https://talktomytrip.com/

## IDEA

Trips don't fail because of one disruption. They fail because travelers are left to coordinate everything that follows. One cancelled flight silently breaks the rest of the trip. Cascade Repairer is a voice agent that notices the break, calls the traveler first, asks permission, and repairs the trip while they're still on the phone: the flight is re-shopped on live Sabre inventory with a guarantee the replacement is a different flight, every downstream leg is repaired in parallel, and the agent calls back with the new flight, the fare difference, and a PayPal refund already sent when the new fare is cheaper. No app opened, nothing changed without a spoken yes.

## IMPLEMENTATION

A traveler books a real flight by voice through a WebRTC orb on the live dashboard (https://talktomytrip.com/). Behind the orb, Vocal Bridge delegates each turn to an OpenAI Agents SDK "Concierge" agent with eight tools — search_flights, book_flight, complete_trip, trip_status, destination_info, check_return_flights, email_itinerary, and fix_trip — so one conversation carries the traveler from a live fare search to a booked trip, an emailed itinerary (the agent spells the address back letter by letter before sending), and what to do in the destination city.

When the flight is cancelled, the system places an outbound phone call BEFORE touching any data: the agent names the exact cancelled flight, confirms nothing has been changed, and asks one question. A ConsentClassifier agent reads the answer from the live call transcript; anything short of a clear yes stands down and touches nothing. On a yes, repairs launch as parallel asyncio background tasks: the flight leg re-shops live Sabre inventory — the cancelled flight is excluded from the candidates, the closest-time alternative wins — while the hotel, ride, dinner, and tour legs run the same repair cascade as simulated services. The dashboard flips each reservation card from broken to repairing to fixed in real time, with the original flight struck through beside its replacement. When repairs settle, the agent calls back, speaks the new flight and the fare difference, and if the rebooked fare is cheaper, the difference has already been refunded to the traveler's PayPal via the Payouts API (sandbox) — spoken on the call and visible in the account. The agent also handles explicit language switching mid-conversation, e.g. summarizing the trip in Japanese on request, then returning to English.

Stack: Python/FastAPI in a Docker container on GCP Cloud Run with containerized CI/CD, a BigQuery status lifecycle (booked → broken + awaiting consent → granted → repairing → fixed → results callback) driving both the agent and the live screen, transactional email from our own domain (info@talktomytrip.com), and a hermetic test suite of 634 tests.

## HOW WE USED VOCAL BRIDGE

Vocal Bridge is the entire voice surface, used in two of its integration patterns. The booking orb is voice for an existing agent: Vocal Bridge runs the conversation over WebRTC and delegates each query to our OpenAI Agents SDK Concierge. The backend then uses voice as a tool, placing two proactive outbound phone calls: the disruption call that captures spoken consent from the live transcript, and the results callback that speaks the true post-repair state. The agent runs the Concierge hybrid pattern — a fast conversational foreground with background reasoning and tools — so it keeps answering questions ("how's my trip?") while repairs run. Multilingual switching is inherited from the platform and gated by explicit request in our prompt.

## HOW WE USED SABRE

OAuth token flow plus InstaFlights (Flight Search API v1) on CERT, returning real priced itineraries with airline, cabin, and duration — presented one option per airline, so the traveler hears a genuine choice. The repair path re-shops the same live Sabre inventory and guarantees a different flight than the cancelled one. Flight shopping and re-shopping are live; PNR writes are simulated, because createBooking isn't entitled on the hackathon CERT credentials — the booking seam is built, so real ticketing is a credentials swap, not a rewrite.

## ROADMAP

The repair engine is disruption-agnostic: delays, gate changes, and hotel failures fire the same consent call, parallel repair, and callback. Next: real inventory for the remaining trip legs (ground transport, dining, experiences), full PayPal checkout on booking with true same-transaction refunds, automated check-in, and company-scale group trips.

## VOCAL BRIDGE CALL SESSION ID

83ce8523-b676-4925-9637-3408b1927500

Outbound call placed by our assistant (the results callback from the demo video, 2026-07-18): 34 seconds, completed, recording available — it speaks the rebooked JetBlue flight, the $80 fare difference already refunded to PayPal, and the email offer.

Vocal Bridge call session ID: 83ce8523-b676-4925-9637-3408b1927500 (Call 2 — results callback, 34s, recorded, from today's video run)