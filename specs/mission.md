# Mission

## The problem

The DeepLearning.AI Voice AI Hackathon — **"The Complete Trip," powered by Sabre and Vocal Bridge** — takes place in person on **July 18, 2026** in Mountain View, CA. The challenge: a real trip is fragmented across flights, hotels, rideshares, dining, and event tickets, each living in a different app that doesn't talk to the others. Teams must prove all of it can be pulled into a **single voice conversation and a single itinerary**, booked and managed by a voice AI agent. Submissions must use **Sabre travel APIs** and the **Vocal Bridge voice layer** to qualify for prizes, and live demos are mandatory.

Hackathon days are short — hacking runs roughly 10:00 AM to 4:00 PM. Teams that spend those hours wiring up infrastructure, deployment, and voice plumbing don't ship. Teams that arrive with a working foundation spend the day on the idea.

## What this project is

This repo is a **hackathon-ready foundation**: a production-grade voice-agent platform built *before* event day, so that on July 18 the team can assemble a working demo fast.

**The team idea is decided** (Discord, 2026-07-06): **the Cascade Repairer** — Pallavi's concept, locked as the anchor. A trip is a chain; when the flight cancels, everything downstream breaks. The demo: a fully booked trip (flight, hotel, ride, dinner, tour) takes a live flight cancellation, and the voice agent *keeps talking to the user while background agents repair all five legs in parallel* — under 60 seconds, with a unified itinerary on screen flipping from broken to fixed. Every other team demos booking-by-voice; we demo a trip breaking and healing itself.

That pitch adds two hard demands the foundation must prove before event day:

1. **Concurrency** — the agent must speak while background repairs run in parallel. Voice-as-a-tool is sequential by default; if that isn't rewired ahead of time, the 60-second moment becomes 3+ minutes of silence.
2. **Live itinerary view** — voice plus a screen flipping broken → fixed *is* the demo moment.

The foundation still guarantees that every building block from the Vocal Bridge / DeepLearning.AI training course is working code here:

- All three voice architectures from the course — cascaded (STT → LLM → TTS), real-time voice-to-voice, and the hybrid "Concierge" pattern — ported from the L2–L5 training notebooks into the backend.
- An agentic LLM layer built on the **OpenAI Agents SDK** (agents, tools, MCP servers), following the patterns already stubbed in `backend/api/hello.py`.
- A productionized deployment path on **Google Cloud Platform** (Cloud Run via Cloud Build CI/CD), reusing the devops and promotion scripts already in this repo.
- Voice-quality evaluation (latency/TTFB, WER, MOS-style checks) so quality is measured, not guessed.

## Who it serves

- **Primary: Josh and his hackathon team** (up to 4 builders). They need working patterns, deploy scripts, and a shared foundation they can extend under time pressure on event day — not a pile of tutorial code.
- **Secondary: hackathon judges and end-user travelers** — served indirectly through a demo that actually works live and a conversation flow a stressed traveler would genuinely use.

## What success looks like

1. **The live demo works end-to-end.** The Cascade Repairer moment lands live: a booked trip takes a flight cancellation, the agent talks the traveler through it while all five legs (flight, hotel, ground, dining, experience) repair in parallel, and the itinerary reads back fully fixed — without breaking. Live demos are "the Vocal Bridge way."
2. **The deployment is production-grade, not a laptop demo.** The agent runs on Cloud Run, stood up through the Cloud Build CI/CD trigger (PR from `vb/feature/*` into `vb/dev`), with real latency and quality metrics observed.
3. **Deep skill mastery.** Fluency in every course module — the three audio architectures through evaluation — and the OpenAI Agents SDK, regardless of hackathon outcome. The training investment pays off whether or not the team places.
4. **The demo fits in a pocket — via direct install; the App Store path is closed** *(added 2026-07-11; revised 2026-07-16 after App Review; settled 2026-07-18)*: **"Talk to My Trip"**, the native iOS companion app (`ios/TalkToMyTrip/`), was submitted to App Review on 2026-07-11 (the Phase 17 full three-act build — access-gated, AI-consent flow, empty-start onboarding included; runbook `IOS_DEPLOY.md`, now historical). Apple rejected v1.0 (3) on 2026-07-16 under Guideline 3.2 because public distribution did not match its limited hackathon-event audience. **The planned Unlisted App Distribution recovery was dropped unshipped on 2026-07-18 (Josh's call, event-day morning)** — chasing re-review filings on event day is not worth it, and the demo never depended on them. The app remains a finished pocket demo **installed directly via Xcode** (TestFlight optional), the web surfaces remain the guaranteed demo path, and no App Store distribution is pursued unless Josh reopens it after the event.

## Non-goals

- Building the *finished* hackathon demo in advance — the foundation proves the hard mechanics (concurrent repair during a live voice session, repair-capable Sabre tools, live itinerary view); the demo polish and final assembly stay event-day work with the team.
- The stretch integrations from the team discussion (Google Maps distances, Uber, Costco Travel bundles) — mocked stretch goals only, and only after the core repair loop works end to end (tracked in `TODO.md`).
- A general-purpose travel product beyond the hackathon's scope — the iOS app ("Talk to My Trip") is a finished limited-audience special-event app installed directly (the App Store path was dropped 2026-07-18), not a public consumer-product pivot.
