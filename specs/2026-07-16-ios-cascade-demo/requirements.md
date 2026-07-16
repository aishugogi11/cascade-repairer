# Requirements — Talk to My Trip: native cascade demo

Build an iOS-only demo experience that carries the proven core flow from
`GET /v1/cascade/` into a clean native SwiftUI screen:

`book by voice → cancel the flight → receive the Vocal Bridge consent call →
approve → watch all five legs repair → receive the Vocal Bridge results call`.

Branch: `vb/feature/ios-cascade-demo`.

This spec was requested as a focused iOS follow-up; it does not insert, reorder,
or mark its implementation as a phase in `specs/roadmap.md`. The 2026-07-16 App
Review replan added a separate, immediate Phase 36 for the same-build unlisted
recovery; scheduling this implementation against Phase 24 remains a separate
decision.

## Scope

### User story

1. After the existing access gate and AI/voice consent, the app opens on a new
   **Demo** tab with no old trip pinned. The traveler taps the native voice orb
   and completes the existing guided booking conversation. The compact
   transcript and native itinerary update as the flight and four downstream
   reservations are booked.
2. Once the flight, hotel, ground transport, dining, and experience are all
   present and confirmed, a visible **Cancel flight** button becomes available.
3. Tapping it disconnects the in-app voice session to avoid an audio conflict,
   then calls `POST /v1/demo/disrupt` for the displayed trip. The app shows a
   dialing state but does not optimistically change itinerary data.
4. The endpoint queues Vocal Bridge Call 1 before breaking the flight. The call
   tells the traveler what was cancelled and asks whether Cascade may rebook the
   flight and recheck the rest of the trip.
5. The app continues to render truth from the 1.5-second status poll:
   `broken + awaiting_consent` shows a waiting treatment with no recovery clock.
   A clear spoken yes changes consent to `granted` and starts the five parallel
   repairs. A no, ambiguous answer, classifier failure, or timeout starts no
   repair and leaves an honest stand-down state.
6. On approval, each card updates live through `repairing → fixed`. The recovery
   timer begins only when the first `repairing` state is observed after consent
   and freezes when no item remains `broken` or `repairing`.
7. The repaired flight card shows the replacement flight and the prior flight's
   struck-through `detail.rebooked_from` line. When all work settles, the app
   shows an all-clear state and the existing backend places Vocal Bridge Call 2
   with the actual repair results.

One successful run uses two outbound calls. A declined/timed-out run uses one.
Booking through the in-app web voice bridge does not consume outbound-call quota.

### App structure

The existing access gate remains above a native two-tab shell:

| Tab | Purpose | Default |
|---|---|---|
| **Demo** | New focused booking → break → consent → repair → callback experience | Yes |
| **Home** | The already-working `ContentView` experience retained for reference and regression comparison | No |

The Home tab keeps its current appearance and behavior, including its itinerary
timeline, recommendation sheet, long-press trip selector, and hidden demo gesture.
It may be refactored to receive shared managers, but it must not be redesigned as
part of this feature.

There must be exactly one `VoiceManager` and one hidden `VoiceWebView` in the app
shell. Both tabs reuse that bridge; the app must never mount two Vocal Bridge
clients or hold two microphone sessions. Changing tabs ends any live voice
session before changing the displayed-trip pin.

### Demo tab surface

```text
NavigationStack
  Talk to My Trip                              New trip
  compact lifecycle banner / recovery timer
  native Vocal Bridge orb
  last few traveler/Cascade transcript lines
  prominent current-flight card
    carrier + flight · PT departure/arrival · fare
    cabin · duration · stops
    struck-through "Was …" line after repair
  compact hotel / ride / dining / experience cards
  safe-area action: Cancel flight
Tab bar: Demo | Home
```

The Demo tab includes only what advances or explains the live story:

- A **New trip** action that ends the live voice session, clears the native demo
  selection, and starts the next booking from an unpinned session. It does not
  delete or mutate the old server-side trip.
- The existing native voice orb states: idle, connecting, listening, speaking.
- A bounded, auto-scrolling transcript showing the most recent traveler and
  Cascade turns. The SDK's existing `transcript` bridge events remain the source;
  the `reply` event remains the trip-refresh signal and must not create duplicate
  lines.
- One prominent flight card and four smaller downstream cards. New cards animate
  in during booking; lifecycle state uses icon, label, and color together.
- One lifecycle banner with plain-language copy for booking, ready, dialing,
  awaiting consent, standing down, repairing, recovered, reconnecting, and error.
- A visible destructive **Cancel flight** action. It is enabled only when the
  complete five-leg itinerary is present, every leg is initially booked, a
  flight exists, and no disrupt request, consent wait, or repair is active. It
  may re-enable after an explicit stand-down so Call 1 can be retried, but not
  after a successful recovered state; **New trip** starts the next full run.
- A 60-second recovery timer that is absent before consent, runs during repair,
  and freezes on completion.

The Demo tab deliberately excludes the web dashboard's traveler profile, recent
trips, disruption score, Sabre search log, candidate side panel, repair activity
feed, downstream-impact panel, and recommendation sheet. The existing Home tab
may continue to expose its current selector and recommendation sheet.

### Existing backend contracts

No new endpoint, backend schema, agent tool, call script, or repair behavior is
part of this feature. The iOS app consumes these existing contracts:

| Endpoint / bridge | iOS use |
|---|---|
| `POST /v1/auth/validate` | Existing access gate; unchanged |
| `GET /v1/mobile_voice/` | Existing hidden WKWebView Vocal Bridge transport |
| `POST /v1/web_call/token` | Server-minted voice token, called by the headless page |
| `POST /v1/web_call/query` | Existing Concierge turn delegation and guided booking |
| `GET /v1/sabre_tools/latest_trip_id` | Detect the newly booked trip after a clean-slate baseline |
| `GET /v1/itinerary/status/{trip_id}` | Poll trip/items/summary plus optional `consent` and rich flight fields every 1.5 seconds |
| `POST /v1/demo/disrupt` | Queue consent call, then break the displayed flight; repairs wait for spoken approval |

The status decoder gains optional native models for fields that already exist:

- `ItineraryItem.details`: `airline`, `flight_number`, `airline_name`, `cabin`,
  `duration_minutes`, `layover_airports`, `arrives_next_day`, and `stops`.
- `ItemDetail.rebooked_from` in addition to the existing `why_chosen`,
  `price_delta`, and `impact`.
- `TripStatusResponse.consent`: `state`, `message`, `since`, and `updated_at`.

Every additive object remains optional. Old trips and partial payloads must render
without placeholders such as `nil`, `unknown`, empty separators, or decode
failures. The Demo tab does not depend on `pending_options`; flight choices remain
voice-first and may be read in the compact transcript.

### Native lifecycle state

One pure state derivation maps the latest poll plus local request state into the
UI. Views must not independently guess the flow.

| State | Source of truth | Required presentation / action |
|---|---|---|
| `booking` | No active demo trip | Orb and short booking prompt; Cancel disabled |
| `building` | New trip exists but all five booked legs have not landed | Cards materialize; “Building your trip”; Cancel disabled |
| `ready` | All five required leg types exist and are initially booked | Confirmed treatment; Cancel enabled |
| `dialing` | Local disrupt request in flight | “Calling you to confirm”; Cancel disabled; no optimistic break |
| `awaitingConsent` | Flight broken + consent `awaiting_consent` | Red waiting treatment; no timer; Cancel disabled |
| `standingDown` | Consent `declined`, `timed_out`, or `error` | Render backend message; no repair claim; permit an explicit Call 1 retry |
| `repairing` | Any item `repairing` after consent | Orange repair treatment, live timer, animated per-item updates |
| `recovered` | At least one item fixed and none broken/repairing | All-clear treatment, frozen timer, Cancel disabled, “Watch for your summary call” |
| `reconnecting` | Poll failed after a trip was known | Preserve last good trip; show non-blocking retry status |

The app never starts repairs itself. It has no native “Approve” or “Repair”
button: the only authorization channel is the traveler's answer on Call 1.

### Clean-slate booking and persistence

- On the first Demo-tab run, or after **New trip**, capture the current
  `latest_trip_id` as a baseline but do not display or pin it.
- Disconnect the voice session, clear the native trip pin and transcript, then
  begin a new Vocal Bridge session with no `trip_id`.
- Recheck `latest_trip_id` after agent replies and on the existing periodic
  cadence. Adopt only a non-empty ID different from the baseline, then persist it
  as the active demo trip so a phone-call interruption, background/foreground
  transition, or app relaunch can resume the same run.
- Clear that persisted demo ID only through **New trip**. The Home tab may retain
  its current “show latest trip” behavior.
- The repository's backlogged Phase 20 removal of the temporary latest-trip
  fallback in `mobile_voice.py` is a hard deployment prerequisite. That fallback
  would otherwise pin a supposedly fresh voice session to the old global latest
  trip. This iOS spec must not work around it with a fake trip ID, JavaScript
  interception, or other client-side sentinel.

### Audio, phone-call, and app lifecycle

- Tapping **Cancel flight** first disconnects the in-app WebRTC voice session,
  preserving the transcript on screen, before sending the disrupt request. This
  prevents the hidden webview from competing with the inbound phone call for the
  microphone/audio route.
- The app observes `scenePhase`. Polling may pause in the background, but becoming
  active after Call 1 or Call 2 triggers an immediate status refresh before the
  normal 1.5-second loop resumes.
- An audio interruption or phone call must leave the orb disconnected rather than
  automatically reconnecting. The user may start another in-app voice session
  only when the demo is not dialing, awaiting consent, or repairing.
- The current demo trip and last good poll remain visible through temporary
  network loss and app backgrounding.

### Request behavior and failure handling

- `demoDisrupt` decodes the existing response (`trip_id`, `item_id`, `call_id`,
  `call_status`, `consent`) and uses an endpoint-specific timeout long enough for
  Vocal Bridge's observed 10–16 second queue time; the generic 10-second API
  timeout is not sufficient.
- On an HTTP error, show the scrubbed backend `error`/`detail` message in friendly
  UI copy. Never surface the callee number, access code, API keys, or raw payloads.
- On an ambiguous client timeout/network failure, do not automatically POST again:
  the server may already have queued a quota-consuming call. Continue polling to
  reconcile a broken/consent state; enable manual retry only after the request has
  settled and the trip still has no new server state.
- A 401 keeps the existing behavior: clear the Keychain code, stop polling and
  voice, and return to the access gate.

## Decisions

- **Core demo only** (Josh, spec interview 2026-07-16): booking first, then a
  visible break/cancel action, Vocal Bridge consent call, approved live repair,
  and Vocal Bridge completion call. Operator analytics stay on the web page.
- **Visible Cancel flight button** (Josh): this is the primary trigger in the
  Demo tab. No confirmation sheet is added to the staged flow; the clear
  destructive label, complete-trip eligibility rule, immediate disabled state,
  and access gate prevent casual activation. The Home tab's triple-tap remains a
  reference fallback, not the Demo tab's required path.
- **Native iOS, proven Vocal Bridge plumbing** (Josh): all visible UI is SwiftUI;
  voice continues through the existing hidden `WKWebView`, native microphone
  permission, `WKScriptMessageHandler`, `vbConnect`/`vbDisconnect`, server-minted
  token, and `/query` delegation. No native Vocal Bridge SDK rewrite.
- **Two tabs, one transport** (Josh): Demo is the new default; Home preserves the
  already-working screen for reference. Sharing one bridge avoids duplicate
  voice sessions and stale trip pins.
- **Polling, not push**: the existing 1.5-second status contract remains the
  complete UI source. No WebSocket, Live Activity, or push-notification work.
- **Server truth over optimistic animation**: Call 1 is queued before the backend
  writes `broken`; consent launches repairs; Call 2 follows settled repair tasks.
  The app reflects those facts and never simulates them locally.
- **Unlisted release posture** (Josh, App Review replan 2026-07-16): the rejected
  v1.0 (3) binary is resubmitted unchanged through Phase 36 for Unlisted App
  Distribution. No new archive or upload occurs while that same-build recovery is
  active. After the unlisted release is approved and Phase 20 removes the bridge,
  this feature may ship as a later update to the same unlisted app record; direct
  Xcode device installs do not affect review.

## Context

- **Design tone:** calm native iOS. Use `NavigationStack`, `TabView`, semantic
  system backgrounds/materials, SF Symbols, generous spacing, and restrained
  indigo accents. Reserve red/orange/green and stronger motion for
  broken/repairing/fixed changes. Do not reproduce the web page's three-column
  density on a phone.
- Support Dynamic Type, VoiceOver labels/hints, sufficient contrast, Reduce
  Motion, and color-independent lifecycle labels/icons. Keep the primary action
  reachable with a safe-area inset on supported portrait iPhones.
- Render itinerary timestamps in `America/Los_Angeles`, labeled `PT`, matching
  the backend/web standing rule; never use the device's local timezone silently.
- User-facing copy is short and honest: “Waiting for your go-ahead” before
  consent, never “repairing”; “Watch for your summary call” after all-clear,
  never a claim that the call was answered.
- Keep iOS 17+, iPhone-only, portrait, SwiftUI + WebKit + AVFoundation, and zero
  third-party dependencies. Preserve the access gate, first-use AI consent,
  privacy manifest, legal/support links, Keychain behavior, and About withdrawal.
- Distribution remains **unlisted**: this is a finished limited-audience
  special-event app installed through a direct App Store link, with the existing
  access gate preventing unauthorized use. It is not a public-search product and
  not a TestFlight substitute.
- The backend is single-operator demo infrastructure. Adopting a changed global
  `latest_trip_id` is acceptable only for this staged flow; multi-user trip
  ownership is out of scope.
- Review the deployed base URL in `APIConfig.swift` during implementation, but do
  not introduce a new backend environment or custom domain in this phase.

## Out of scope

- Any backend production-code, prompt, endpoint, data-schema, call-script, Sabre,
  repair, consent-classifier, or Cloud Run change.
- Implementing Phase 20 inside this branch; it is an explicit prerequisite owned
  by its existing backlog phase.
- Rebuilding `/v1/cascade/` inside a webview or embedding any visible web UI.
- Recent-trip browsing, disruption score, Sabre logs, candidate panels,
  recommendation/downstream sheets, or an activity feed in the Demo tab.
- User accounts, Sign in with Apple, per-user trip storage, notifications, Live
  Activities, iPad, landscape, Android, or a native Vocal Bridge transport.
- App Store archive/upload/release, roadmap edits, or replacing the binary in the
  Phase 36 same-build unlisted recovery.
