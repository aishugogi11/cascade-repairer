# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (late-night replan):** Phase 21 (voice booking page) is merged, deployed, and QA'd, and **Phase 17 is complete** — the full three-act build was submitted to App Review 2026-07-11; per `mission.md` #4 approval is a bonus, the web surfaces are the demo path, and no new binary is uploaded until the in-review one is approved (BACKLOG Phase 20). Details in [changelog.md](changelog.md). **Restoration note:** this replan re-restores the 2026-07-12 evening replan's roadmap (PR #34, commit `4ac1bb0`), which the booking-page branch's merge resolution (PRs #35/#36) had silently reverted — Phase 17's completion and Phases 22–24 below were lost from this file for a few hours; if a roadmap statement conflicts with the changelog, trust the changelog. Open work, in order: the cascade dashboard (Phases 22–23) on the visual frame Phase 21 established, then pre-event readiness (Phase 24 — **time-gated, not order-gated**: pull the Sabre-keys work ahead the moment the keys arrive, expected Monday 2026-07-13).

**Update 2026-07-13 (Phase 25 archived):** the Sabre CERT exploration ran the same day the keys landed and is archived to [changelog.md](changelog.md) with caveats — headline finding: **real shopping, mock booking** (Flight Search API v1 entitled with real priced itineraries; `createBooking` entitlement-blocked at `PassengerDetailsRQ`; full matrix and demo recommendations in `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`). Its independent validation returned **FAIL**; the fixes shipped as **Phase 26** and the close-out re-validation passed 2026-07-14 (both archived to [changelog.md](changelog.md)). The deal-manufacturing upsell engine stays backlogged in [BACKLOG.md](BACKLOG.md) (revisit after Phase 23, minimum slice `extend_stay`); its API-entitlement gate is now answered **go**.

**Replan 2026-07-13 (evening; updated 2026-07-14):** the Phase 25 findings reshaped the tail of the roadmap. Order: **27 (real search in the demo path) → 22 → 23 → 24** (Phase 26, validation fixes, is complete and archived). All four validation-triage decisions were answered at the replan interview (targeted sweep additions, executed dummy-PNR probe for modifyBooking, empty-set PNR hygiene, dated re-run artifact); the frozen-client bug fixes (dead `POS` field, empty-BFM response shapes, BM errors-as-200 masking) are deliberately **conditional Phase 24 work** — they only matter if Sabre grants BFM content / booking entitlement, realistically via the event-day ask. One Phase 26 item remains open and rides with Phase 24: the **different-day `pytest -m cert` dated artifact** appended to `sabre-cert-notes.md` (D4 — event-day morning at the latest).

**Replan 2026-07-14 (evening — real data everywhere reachable):** Phase 27 shipped, deployed, and spoke real CERT fares on Cloud Run the same day, but its independent validation returned **FAIL** with two code defects (unmapped *connection* airports pass the parser; the mock's Pacific-fiction clocks are re-read as airport-local, so mock west-to-east arrivals precede departures) — those are now **Phase 28**. Two strategic facts landed the same evening (tech-stack § entitlement addendum): InstaFlights content is **per-pair** (113 of 731 supported pairs had +2-day content, so near-term real repair shopping is possible today), and **the Sabre entitlement-ask route is closed** (decision 2026-07-14) — Sabre's newer flightShop/flightShopLite are entitled-but-empty on this PCC and the MCP Server pilot can't bypass entitlements, so no unlock is coming. The cascade's credibility therefore rides on **Phase 29**: the flight-repair leg re-shops real InstaFlights data. Phases 27 and 28 shipped and deployed 2026-07-14 and are archived to [changelog.md](changelog.md). Phase 24's "event-day ask" bullet and its conditional BFM/booking punch list are deleted with the decision (the punch-list items remain documented in the Phase 25 notes if circumstances ever change).

**Replan 2026-07-14 (late night — Phase 28 close-out):** Phase 28's independent validation returned **FAIL** on acceptance-package gaps while every behavior criterion passed (report: `specs/2026-07-14-search-hardening/validation-report.md`) — criterion 6 needs all six committed metro-alias cases and the token-refresh tests cover only the GET path; the report also surfaced one real behavior risk (an empty repeat search leaves the previous options bookable) and one tooling hazard (`git_pull_dev.sh` defaults its merge base to `main`, not `vb/dev`, and merges with `--admin`). Those four items are **Phase 30**, a small close-out landing before Phase 29 builds on the search path (the Phase 26 precedent). Constitution updates from the same evening: the documented no-results 404 is now an honest empty (never a mock swap), 401s refresh the token once, `AIRPORT_TZ` covers the full live supported-markets list (metro + non-US codes) under a cert parity test, and the pair menu shifts **as the UTC day rolls** (00:00 UTC = 5 PM PDT) — evening rehearsals cross that boundary, sharpening the Phase 24/29 morning-smoke rule. Process lesson carried into Phase 30's spec: PR evidence must be in the description **pre-merge** (the validator's four `validation.md` gap questions are that spec interview's input). New order: **30 → 29 → 22 → 23 → 24**.

**Update 2026-07-15 (Phase 30 shipped):** the search-hardening close-out is complete, merged (PR #47), deployed, and archived to [changelog.md](changelog.md) — all four remediation items landed and the bare suite is green (387 passed). Its independent validation returned **FAIL** on two non-code items only, both re-verified as environmental: an empty PR #47 description (DoD-B — the pre-merge-evidence gap, now superseded by the `pr-evidence-guard` workflow, PR #48) and a live CERT priced-search test that hardcodes DFW→LAX +30d and drifted to honest-empty (JFK→LAX +30d returns real fares through the identical path). One brittle-test residual, now **folded into Phase 24** (2026-07-15 replan decision — see its CERT-tripwire bullet): the cert priced-search tripwire pins a single pair/date (DFW→LAX +30d), so it reds on morning-smoke purely from cache drift; Phase 24 de-brittles it. The same replan reconciled the constitution to the thin/volatile cache reality (tech-stack § 2026-07-15 addendum: JFK→LAX is the current verified demo anchor; the 2026-07-14 menu is stale) and narrowed Phase 22's `_LATEST_SEARCH` hardening to age-expiry only (Phase 30 already clears on non-optioned returns).

**Update 2026-07-15 (Phase 29 shipped; QA closed by the evening's Phase 31 rerun):** the real-repair pivot is implemented, merged (PRs #51/#52), and archived to [changelog.md](changelog.md) — the flight-repair leg now re-shops real InstaFlights data (BFM → `instaflights_search`), PNR writes stay mock, and the shared `FlightOption` parser is extracted to `backend/api/flight_options.py`. Its independent validation returned **FAIL on the acceptance package only** (DoD-B: PRs #51/#52 carry placeholder descriptions, not the required pre-merge mock/CERT snippets; local mock-mode BigQuery walkthrough untestable) — every implementation criterion passed and the bare suite is green (405 passed); **manual QA closed 2026-07-15 (evening PT)** — the Phase 31 live rerun drove the repair re-shop end to end on the deployed service (a real cancelled flight rebooked onto a *different* real InstaFlights flight, spoken by Call 2). Phase 24's morning-smoke keeps its Phase 29 rider regardless (probe the scripted pair's repair re-shop route on demo morning — cache windows drift).

**Update 2026-07-15 (Phase 22 shipped, QA'd, archived):** the consolidated cascade dashboard (`GET /v1/cascade/` — repair surfaces, disruption score, downstream impact, on-page demo triggers, Phase 23 voice placeholder, item-H age expiry) is merged (PR #53), deployed, manually QA'd on Cloud Run the same day, and archived to [changelog.md](changelog.md). Its independent validation returned **FAIL on the acceptance package only** (DoD-B again: PR #53 placeholder description; report in the spec dir). **QA produced the Phase 23 demo contract** (settled with Josh 2026-07-15): booking by voice, consent-gated repairs read from the VB transcript, the timer anchored at the spoken yes, real-trip call scripts, and a results callback.

**Update 2026-07-15 (evening — Phases 23 and 31 shipped and archived):** Phase 23 (live voice surfaces + the consent-gated demo flow, PR #54) and its same-day close-out Phase 31 (PR #55 — the `room_name` session join that unblocks Call 2, the different-flight rebooking guarantee, the re-trigger race, `trip_status` honesty, the `fix_trip` phone deferral, and the hardened PR-evidence guard) are merged, deployed, and archived to [changelog.md](changelog.md). **Manual QA closed the same evening (2026-07-15 PT): the live rerun PASSED** on the post-31 deploy (commit `2637754`) — booked by voice through the on-page orb, Call 1 asked consent from the real trip's data, the spoken yes granted and launched repairs with the timer anchored at the go-ahead, and **Call 2 arrived speaking a different rebooked flight**. Both phases are fully complete. Two same-evening riders shipped on `vb/dev` ahead of the rerun (commits `1ac2659`/`2637754`, both deployed): the Phase 31 validation's fixes (the missing `broken`-status trip_status test; the max-instances roadmap correction — the service-level cap was already `1`) and the **New trip clean-slate control** — the rerun's first attempt hit a client-side rebuild of the Phase 18 pin trap (the orb pins every fresh session to the displayed trip, making guided booking unreachable), fixed by a header control that clears the display, ends the live voice session, and re-adopts only a newly booked trip; README carries the operator run sheet. Open work: **Phase 24**.

**Replan 2026-07-16 (constitution reconciled to the shipped one-page demo):** tech-stack now records what Phases 22–23/31 made true — `/v1/cascade/` is the demo's primary surface (the two-button `/v1/demo/` page is a kept backup, decision at this replan), the demo orchestrator is the consent-gated flow with the `room_name` session join, the Concierge carries `trip_status` / flight-identity stamping / the `fix_trip` phone deferral, the repair re-shop guarantees a different rebooked flight, the single-instance guarantee is the *service-level* Cloud Run cap, and `git_pull_dev.sh` is the PR-evidence guard (convention, not enforcement). Phase 24 gains four small items from this cycle's validation/QA findings (fast-fail `place_call`, `?code=` GET support on the gate, and the two invariant tests). `mission.md` unchanged — scope and audience didn't move.

*(The PR #55 evidence-backfill follow-up was dropped 2026-07-16 — the live-run evidence already lives in the Phase 23/31 spec dirs and changelog, and the pre-merge guard now covers future PRs; retroactively filling a merged PR's description recovers nothing.)*

**Triage 2026-07-16 (TODO → roadmap):** the four items that accumulated in `TODO.md` after the live QA rerun all promoted, one phase each, settled at the triage interview: features land ahead of Phase 24 (which stays the final, largely event-day-gated readiness gate — its "pull ahead when ready" character unchanged). New order: **32 (repair result reflected on the page) → 33 (rich flight fields) → 34 (return-flight verify-only check) → 35 (Tavily destination info) → 24**. Phase 33 deliberately precedes Phase 34 — the rich fields are what make Phase 34's spoken return example credible. Phases 34 and 35 are the first to cut if the clock runs short (34 is explicitly data-gated and cuttable per its own scoping; 35 is a nice-to-have conversational garnish).

**Update 2026-07-16 (Phase 32 shipped, QA'd, archived):** the repaired-flight fix is merged (PR #58), deployed, manually QA'd on the deployed service the same day (two break → repair cycles, was-line and exclusion re-stamp verified), and archived to [changelog.md](changelog.md) — the cascade page now shows the rebooked flight with the original struck through. Its independent validation returned **FAIL on the acceptance package only** (DoD-B, again: PR #58 merged with placeholder evidence sections; report and two adopted validator tests in the spec dir). Open order: **33 → 34 → 35 → 24**.

**Replan 2026-07-16 (evening — Phase 32 close-out):** four decisions, all settled at the replan interview. (1) **PR evidence retires as a merge gate** — commit `933f8e8`'s removal of the `git_pull_dev.sh` guard is accepted, not restored: every validation since Phase 28 FAILed on exactly this paperwork while never catching a behavior defect, and the evidence already lives in each spec dir + changelog entry (tech-stack § Deployment records the convention; future `validation.md` files must not require PR-body evidence, retiring the recurring DoD-B). Phase 24's guard-test sub-item is deleted as moot. (2) The **Phase 32 write-back contract is recorded in tech-stack** (§ Backend): the repair rewrites the flight item's row wholesale — `details` included — which became a **Phase 33 scoping constraint** (honored: the shared stamp is a tested parity invariant). (3) The validator's **partial-write risk is accepted** (bookings insert precedes the field write; a failed field write strands an inert booking row while the repair honestly errors) — noted in tech-stack, no rollback machinery at demo scale. (4) `DEMO_FLOW.md`'s "current Phase 32 gap" paragraph is refreshed to the shipped behavior. `mission.md` unchanged.

**Update 2026-07-16 (Phase 33 shipped, QA'd, archived):** rich flight fields (airline name, cabin, duration, layovers, next-day flag — through the parser, both `details` stamping paths, the spoken clause + on-request reference block, and the cascade card/candidates) are merged (PR #60), deployed, manually QA'd live the same day (real JFK→LAX CERT fares spoken with airline names), and archived to [changelog.md](changelog.md). Its independent validation returned **PARTIAL** — all automated criteria pass; the interactive walkthrough criteria were headless-untestable and closed by the operator's live QA (report in the spec dir). A same-day rider (PR #61) pinned the Concierge's first turn to a short greeting. Same-day probe reality check: the July 21 pair menu is **JFK→LAX only** (probe loop run 2026-07-16 — every other shortlist pair honest-empty, including the **reverse pair LAX→JFK**, so **Phase 34's data gate is currently dry**; re-check at the Phase 24 morning smoke before building or cutting 34). Open order: **34 → 35 → 24**.

## Phase 34: Return-flight availability check (verify-only)

A new read-only Concierge tool that answers "can I get back?" without booking anything or leaking bookable options into session state. **Explicitly cuttable** if the reverse-pair cache or the clock doesn't cooperate.

> **TODO:** Return-flight availability check in the guided booking flow — re-scoped
> 2026-07-16 (settled with Josh, second pass): **verify-only — no return booking,
> no return options displayed**. The flow: after the outbound is booked, the
> agent asks when the traveler plans to come back; on their return date it
> checks the **reverse pair** and speaks the answer — "yes, there are flights
> back that day, including \<example\>" — or, if the cache is honest-empty for
> that date, says so and offers to check a nearby date (retry adjacent dates).
> Implementation shape: a **new read-only tool** (e.g. `check_return_flights
> (return_date)`) that derives the swapped route from the pinned trip and calls
> `instaflights_search` directly, returning only a speakable summary. Do NOT
> reuse `search_flights` — it stores options in `_SESSION_FLIGHT_OPTIONS` /
> `_LATEST_SEARCH`, which would make return options bookable (book_flight would
> create a second new trip) and leak them onto the booking page's poll. Zero
> changes to the trip model, `_booking_writes`, or the never-book-once-booked
> rule; pairs with item 3 (rich fields make the spoken example credible —
> airline, flight number, nonstop, time).
> **Data pre-check (gating)**: InstaFlights caches are per-pair per-date-window —
> outbound content does NOT imply return content. Before demo day, verify the
> scripted pair has BOTH directions cached at the scripted dates (README
> "Demo-day: check which flight pairs are live" curl loop); fold the reverse-pair
> probe into the Phase 24 morning smoke. This item stays **explicitly cuttable**
> if the data or the clock doesn't cooperate.

## Phase 35: Tavily destination-info tool for the Concierge

One trip-aware `destination_info(question)` tool answering "what's happening there / things to do" with live Tavily results during the call — conversational only, no real hotel/dining/experience booking. Deployment surface: `tavily-python` dep + `TAVILY_API_KEY` on Cloud Run.

> **TODO:** Tavily destination-info tool for the Concierge — added 2026-07-16 (proof:
> `jupyter_notebook/agent_search.ipynb`, working Agents SDK agent + `tavily_search`
> function tool, same SDK/model/pattern as the Concierge). Scope settled with Josh:
> **conversational only — no real hotel/dining/experience booking** (those APIs
> aren't coming; `complete_trip`'s mocked build-out stays exactly as-is). Add ONE
> new trip-aware tool (e.g. `destination_info(question)`) to `build_agent` that
> appends the pinned trip's destination + dates to the query server-side and
> answers "what's happening there / things to do during my trip" with live Tavily
> results during the initial call. A second tool (weather / dining recs) is a
> stretch goal only if the first rehearses reliably — every extra tool is another
> mid-demo model choice. House rules: tool body try/excepts and returns a
> speakable string on failure; condense results for voice (`include_answer=True`);
> start with `search_depth='basic'` (advanced can take seconds inside a live
> voice turn). Deployment surface: `tavily-python` in backend deps +
> `TAVILY_API_KEY` on Cloud Run — the one piece code alone can't ship.
> Blast radius otherwise: one tool registration + instruction sentences; trip
> model, booking writes, repair cascade, consent flow all untouched.

## Phase 24: Pre-event readiness

The residuals that survived Phase 17's completion, re-scoped at the 2026-07-13 evening replan and again 2026-07-14 (evening): **the full `SABRE_MODE=real` flip shipped with Phase 27** (search real on Cloud Run since 2026-07-14), and **the event-day entitlement ask is deleted** — decision 2026-07-14: no extra permissions are coming, so the former "conditional punch list" (dead `POS` field, empty-BFM shapes, BM errors-as-200, BFM offset-bearing time conversion) is retired from this roadmap; it stays documented in the Phase 25 notes' deltas if circumstances ever change. Everything here must land before July 18.

- **Event-day-morning Sabre smoke** (per replan decision D4; extended by the 2026-07-14
  evening replan): `probes/auth_check.py`, then `pytest -m cert`, then `probes/sweep.py`,
  then **probe InstaFlights for the scripted demo pair at the scripted date** — the
  manual form now exists and shipped 2026-07-15 (README "Demo-day: check which flight
  pairs are live" — the `/v1/web_call/query` curl loop; unique `session_name` per call).
  Phase 29 rider: per-pair cache windows shift hour-to-hour, so a green +30d sweep does
  not prove the demo date, and the scripted pair's **repair route** must be probed too.
  Phase 34 rider (2026-07-16 triage, applies only if Phase 34 ships): probe the scripted
  pair's **reverse direction** at the scripted return date too — outbound content does
  not imply return content.
  Detects overnight credential resets and entitlement drift before the first rehearsal;
  append the dated output to the Phase 25 notes (this may also be what closes Phase 26's
  different-day repeatability item).
- **Sweep drift detection** (2026-07-14 replan, from the Phase 26 close-out report): the
  sweep's exit code trips only on `NETWORK-ERR` — `SERVER-ERR` or a changed classification
  (e.g. InstaFlights flipping to 403 after a credential reset) still exits 0, so the
  morning smoke could look green while entitlements regressed. Teach `sweep.py` an
  expected-classification check against the notes matrix (exit nonzero on deviation,
  with the availability/exchange 403↔404 gateway flap treated as one class) so the D4
  smoke is a real drift alarm, not just a network check.
- **CERT priced-search tripwire brittleness** (2026-07-15 replan, Phase 30 close-out):
  `test_sabre_cert.py::test_instaflights_search_returns_real_priced_itineraries`
  hardcodes DFW→LAX +30d and **reds on cache drift alone** — proven 2026-07-15 (that pair
  honest-empty while JFK→LAX +30d returned real fares through the identical path), so the
  morning `pytest -m cert` step can false-alarm even when the code is healthy. De-brittle
  it: probe the verified anchor (JFK→LAX) and/or try several pairs, skip/xfail when all are
  drifted-empty, so a red means the code broke — not that the cache emptied.
- **Async test hygiene** (2026-07-14 replan, same report): the bare suite emits six
  unawaited-coroutine `RuntimeWarning`s across the concierge/repair tests (pre-Phase-26
  debt). Chase them to their fixtures/mocks and fix or properly close the coroutines —
  they can mask async cleanup defects in the exact code that keeps the agent talking
  during repairs.
- **Single-instance cap: verified, leave it alone** (Phase 31 validation, 2026-07-15):
  the service-level `run.googleapis.com/maxScale` is already `1` — the enforced cap
  protecting the in-process consent/session/search-log state. The revision-level
  `autoscaling.knative.dev/maxScale: 100` annotation is a cosmetic default that does
  NOT override it; an operator "fixing" that knob is the actual risk. Morning smoke
  may re-confirm with `gcloud run services describe vocal-bridge-be-dev
  --format='value(metadata.annotations."run.googleapis.com/maxScale")'`.
- **Fast-fail `place_call` without a session key** (2026-07-16 replan, from the Phase 31
  validation's risk list): a successful `vb call` that returns neither `call_id` nor
  `room_name` currently lets the disrupt succeed and the consent watcher drift to its
  3-minute timeout. Make disrupt 502 (before the break, before quota-relevant state)
  when the call payload carries no usable session key — a fast, visible failure
  instead of a demo-day mystery stall.
- **Access gate: accept `?code=` on GET requests** (2026-07-16 replan, from live-QA
  friction): the JSON endpoints are header-only, so browser debugging 401s even with
  the code in the URL. Teach `access_gate.py` to also read `?code=` on GETs (+ tests,
  + a README note) — codes already ride in page URLs, so marginal exposure is nil for
  a shared demo secret, and phone/browser debugging on event day gets much easier.
- **Consent-launch invariant test** (2026-07-16 replan, the validator's proposal): an
  AST test asserting no `await` sits between the consent grant
  (`consent.resolve(...GRANTED)`) and `launch_trip_repairs` in
  `_watch_consent_then_repair` (the race fix's structural property —
  source-inspected only today). *(The companion `git_pull_dev.sh` evidence-guard
  test was dropped at the 2026-07-16 evening replan — the guard itself was
  deliberately removed by commit `933f8e8` and PR evidence retired as a merge
  gate; see tech-stack § Deployment.)*
- **Device QA** (kept as a pre-event item at the 2026-07-12 replan): the three acts on a
  physical iPhone via Xcode install — does not touch the in-review binary
  (`SABRE_MODE=mock`; one run = 2 outbound calls, 10/day quota), sheet & gestures, edge
  cases (Phase 17 validation.md § 7).
- Review the hardcoded dev Cloud Run URL in `APIConfig.swift`.
