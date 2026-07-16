# Validation — Talk to My Trip: native cascade demo

## Preconditions

- Phase 36's unchanged v1.0 (3) resubmission has been approved for Unlisted App
  Distribution before any new binary is uploaded. Direct Xcode installation is
  allowed; this validation does not authorize an App Store upload.
- Backlogged Phase 20 has removed the temporary `mobile_voice.py` latest-trip
  fallback on the deployed backend. A clean-slate Demo session must send no old
  trip pin. If the fallback is still deployed, end-to-end booking-first
  validation is **blocked**, not waived and not worked around in native code.
- `DEMO_ACCESS_CODE`, OpenAI, Sabre, and Vocal Bridge configuration are healthy;
  the demo callee is the physical iPhone being tested; Cloud Run remains capped
  at one instance for in-process consent/session state.
- Confirm remaining Vocal Bridge quota before manual runs. Budget: two calls for
  the yes-path and one call for the no-path.

## Automated

Build the app and test bundle without signing, keeping DerivedData outside the
repository:

```sh
xcodebuild \
  -project ios/TalkToMyTrip/TalkToMyTrip.xcodeproj \
  -scheme TalkToMyTrip \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /private/tmp/TalkToMyTripDerivedData \
  CODE_SIGNING_ALLOWED=NO \
  build-for-testing
```

Run tests on any available iPhone simulator (replace the placeholder with a UDID
from `xcrun simctl list devices available`):

```sh
xcodebuild \
  -project ios/TalkToMyTrip/TalkToMyTrip.xcodeproj \
  -scheme TalkToMyTrip \
  -destination 'platform=iOS Simulator,id=<AVAILABLE_IPHONE_UDID>' \
  -derivedDataPath /private/tmp/TalkToMyTripDerivedData \
  CODE_SIGNING_ALLOWED=NO \
  test
```

All tests pass. Required assertions:

### Payload decoding

- A deployed-shape status fixture decodes trip, all six item statuses, summary,
  optional consent, rich flight `details`, and `detail.rebooked_from`.
- Omitting `consent`, `details`, `detail`, or individual rich-flight fields still
  decodes and produces no empty separators or placeholder copy.
- `DemoDisruptResponse` decodes only the existing sanitized fields; API error
  presentation never includes access code, phone number, or raw response data.

### Lifecycle state and controls

- No active demo trip → `booking`; a partial set of booked legs → `building`.
- Cancel is disabled until all five required leg types are present and initially
  booked with a flight, then enabled in `ready`.
- A local POST in flight → `dialing` without mutating an item status.
- `broken + awaiting_consent` → `awaitingConsent`, Cancel disabled, timer absent.
- `declined`, `timed_out`, or `error` → `standingDown`, no repair claim, explicit
  retry eligible.
- Any `repairing` item after consent → `repairing`; no broken/repairing items plus
  at least one fixed item → `recovered`, with Cancel disabled until New trip.
- A poll failure preserves the last good payload and maps to non-blocking
  `reconnecting` rather than clearing the trip.

### Clean slate and session ownership

- Initial/reset latest ID is stored only as a baseline and is neither displayed
  nor passed to the voice bridge.
- Re-reading the same latest ID does nothing; a changed ID is adopted once,
  persisted as the active demo, pinned to voice, and starts one poll loop.
- New trip disconnects voice, clears the demo transcript/active ID/timer, captures
  a new baseline, and never calls a delete or booking-mutation endpoint.
- Tab switching disconnects before changing trip pin, and the view tree owns one
  `VoiceManager`/`VoiceWebView`, not one per tab.

### Timer, formatting, and request safety

- `broken` and `awaiting_consent` never start the timer.
- First `repairing` after approval starts it; all-clear freezes it; a failed poll
  does not reset it.
- UTC fixture timestamps render in `America/Los_Angeles` with `PT`, independent of
  the simulator's timezone; next-day, stops/layovers, duration, and fare omit
  cleanly when absent.
- `demoDisrupt` uses its longer endpoint-specific timeout. A timeout/network
  ambiguity causes no automatic second POST; the manager waits for poll
  reconciliation before exposing retry.
- A 401 invokes the existing access-code rejection path and stops voice/polling.

## Manual — no outbound quota first

1. **Access and privacy regression:** fresh install shows the access gate; wrong
   code is friendly; correct code unlocks; first orb tap shows the existing
   processor consent before the mic; withdrawing consent from About disconnects
   voice. Rotation still returns to the gate on the next 401.
2. **Tab shell:** Demo is selected on launch; Home retains the current visual
   screen, timeline, card sheet, long-press selector, and hidden gesture. Repeated
   tab switches do not duplicate audio, mic indicators, transcript events, or
   polling loops; a live session disconnects before the switch.
3. **Clean start:** with older trips on the backend, Demo shows no old trip. Tap
   the orb and begin guided booking; the first agent turn behaves as an unpinned
   booking conversation rather than describing/refusing work on the old latest
   trip.
4. **Booking:** complete the day-of verified route/date script, hear 2–3 real
   options, choose one by voice, and watch the new flight and four downstream
   cards materialize. The compact transcript shows current turns without agent
   duplicates. Cancel stays disabled until all five legs are settled, then
   enables.
5. **New trip:** after booking, tap New trip. It disconnects, shows a clean
   booking state, leaves the old backend trip untouched, and adopts only the next
   newly booked trip—not the previous latest one.
6. **Lifecycle resilience:** toggle airplane mode after a good poll; the trip
   remains visible with Reconnecting. Restore connectivity and verify an
   immediate recovery. Background/foreground the app and verify one immediate
   poll followed by the 1.5-second cadence.
7. **Native quality:** check the smallest and largest supported portrait iPhones,
   largest accessibility Dynamic Type, VoiceOver navigation/actions/status
   values, Increase Contrast, Reduce Motion, and a non-Pacific device timezone.
   The Cancel action remains reachable and times still say PT.

## Manual — full Vocal Bridge yes-path

Use a physical iPhone and record the trip ID and remaining quota before starting.

1. Start clean in Demo and book the complete five-leg trip through the orb.
2. Tap **Cancel flight** once. The orb disconnects, the button disables, and the
   app says it is calling. No item changes before the server poll reports it.
3. Receive Call 1 on that iPhone. The call names the actual cancelled flight and
   asks one clear permission question. While waiting, the app's state is
   `broken + awaiting_consent`; no timer runs.
4. Say a clear yes and end the call. Return to the app. It immediately refreshes,
   shows consent granted/repairing, starts the timer on the first repairing poll,
   and animates each of flight/hotel/ground/dining/experience independently.
5. Confirm the flight card changes to a different replacement where Sabre data
   permits, shows its carrier/flight/PT time/fare/rich facts, and strikes through
   the prior `Was …` line. No card can show fixed over stale original details.
6. When no item is broken/repairing, the timer freezes, the app reads all-clear,
   and the UI says to watch for the summary call.
7. Receive Call 2. It names the actual replacement flight/fare difference when
   available and honestly summarizes downstream results. Returning to the app
   preserves the repaired state and frozen duration.

Pass criteria: one tap caused exactly two outbound calls; repairs began only
after the spoken yes; all visible states came from the backend poll; the app
survived both phone-call interruptions without restart or stale pinning.

## Manual — decline/ambiguous path

1. Start with a separate ready trip and tap Cancel once.
2. On Call 1, clearly decline (or run one deliberately ambiguous response if
   quota permits). End the call and return to the app.
3. The app renders the backend stand-down message; the flight remains broken;
   no item becomes repairing/fixed; no timer starts; Call 2 never arrives.
4. The visible action becomes eligible for a deliberate retry. Do not auto-retry
   and do not spend a second Call 1 without the tester tapping it.

## Failure and edge checks

- Attempt Cancel with only a flight/partial build-out: action remains disabled
  and no request is sent.
- Simulate a disrupt HTTP 5xx before any accepted server state: show a friendly
  retryable error and keep server-derived itinerary truth.
- Simulate a client-side timeout after POST: continue polling and never issue an
  automatic duplicate. If `broken/awaiting_consent` appears, treat the original
  request as accepted.
- Force a poll decode fixture with no rich fields and an older trip: card remains
  useful and no literal nil/unknown/empty punctuation appears.
- Relaunch during `awaiting_consent` or `repairing`: the persisted demo trip
  resumes, refreshes immediately, and does not baseline it away as a new trip.
- Mic denial leaves trip viewing and the Home tab usable and gives a clear route
  to Settings; it never triggers a call or crash.

## Tone check

- Before approval: “Waiting for your go-ahead,” never “repairs underway.”
- During repair: short active labels tied to real item states.
- After all-clear: “Watch for your summary call,” not “the call succeeded.”
- Errors are human and actionable; no HTTP dump, secret, airline/fare code in
  prose, or internal tool name reaches the traveler.
- The Demo tab feels like a native travel companion, not a compressed admin
  dashboard; lifecycle motion supports the story without ignoring Reduce Motion.

## Definition of done

- Requirements and the lifecycle state matrix are covered by passing XCTest
  assertions; the app and tests compile with zero third-party dependencies.
- The current Home tab is preserved and the app owns exactly one Vocal Bridge
  bridge across both tabs.
- Both target configurations compile `LSApplicationCategoryType` as
  `public.app-category.travel`, matching App Store Connect rather than the
  rejected build's mistaken Business bundle category.
- Clean-slate guided booking, visible Cancel, consent wait, approved parallel
  repair, repaired-flight result, and the two-call finale pass on a physical
  iPhone against the deployed backend.
- Decline/timeout behavior makes no repair and no Call 2, and is safely retryable.
- Accessibility, phone-call interruption, network recovery, PT formatting, 401,
  and duplicate-call safeguards pass.
- No backend production file, roadmap file, or App Store submission was changed
  by this iOS-only feature. Phase 20 is completed separately before deployment,
  and no replacement binary is uploaded while the Phase 36 unlisted recovery is
  active.
