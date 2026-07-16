# Plan — Talk to My Trip: native cascade demo

The implementation is iOS-only and preserves the deployed backend contract. The
order first makes state and transport ownership safe, then builds the booking
surface, then adds the quota-consuming disruption flow, and only then polishes
and runs device rehearsals.

Phase 20's removal of the temporary `mobile_voice.py` latest-trip fallback is a
deployment prerequisite, not a task in this branch. Do not substitute a fake
trip ID or injected JavaScript workaround.

## 1. App shell — two tabs, one Vocal Bridge bridge

1.1 Introduce a native `MainTabView` (or equivalently named shell) after the
    existing access gate, with **Demo** selected by default and **Home** second.
1.2 Move the current `ContentView` body into a `ReferenceHomeView` without visual
    redesign or behavior removal. Keep its timeline, recommendation sheet,
    About entry, long-press selector, and hidden gestures working.
1.3 Hoist one `VoiceManager` and one 1×1-point `VoiceWebView` into the app shell.
    Inject the shared manager into both tabs; never instantiate a voice webview
    per tab.
1.4 On a tab change, disconnect a live voice session before forwarding the newly
    active tab's optional trip pin. Keep microphone/AI consent and withdrawal
    app-wide, not duplicated per tab.
1.5 Give each tab its own trip-display manager and start/pause its polling with
    tab selection. Switching tabs must not create duplicate polling loops or
    mutate either tab's selected trip.

## 2. Models and deterministic demo state

2.1 Extend the existing optional decoders in `APIService.swift`:
    `FlightDetails`, `ItemDetail.rebooked_from`, `ConsentStatus`, and optional
    `TripStatusResponse.consent`. Keep every new field optional so old rows and
    omitted best-effort blocks still decode.
2.2 Add `DemoDisruptResponse` for the existing success payload and a small
    sanitized API-error shape for `error`/`detail`; do not expose transport
    secrets or raw response dumps in UI state.
2.3 Extract a pure `DemoLifecycleState` derivation over local request state,
    persisted active trip, item types/statuses, summary, and consent. Encode the
    state/eligibility table in `requirements.md` once and make views consume it.
2.4 Add one Pacific formatter for itinerary timestamps and duration/fare helpers.
    Always render `America/Los_Angeles` with a `PT` label; omit missing facts and
    separators cleanly.
2.5 Add a lightweight persisted `DemoSessionStore` for only the active demo trip
    ID and clean-slate baseline. No transcript, access code, or private call data
    belongs in UserDefaults.

## 3. Booking-first Demo tab

3.1 Add `DemoFlowManager` using the existing `APIService`: when there is no
    persisted active demo, read `latest_trip_id` into a baseline without
    displaying it, leave the voice pin nil, and start in `booking`.
3.2 On agent `reply` events and the periodic latest-trip check, adopt only a
    non-empty ID different from that baseline. Persist it, forward it through
    `VoiceManager.setTrip`, and begin the existing 1.5-second status poll.
3.3 Implement **New trip**: unavailable while dialing/awaiting/repairing; otherwise
    disconnect voice, stop/reset the demo poller, clear transcript and persisted
    demo ID, capture a fresh latest baseline, clear the page's native pin, and
    return to `booking`. Never delete the old server trip.
3.4 Build the native Demo layout: compact lifecycle banner, existing orb,
    bounded/auto-scrolling transcript, prominent flight card, compact four-leg
    reservation list, and safe-area action area.
3.5 Use existing bridge `transcript` events for displayed turns. Cap retained
    lines to a small fixed number and use `reply` only for speaking animation and
    trip discovery so agent text cannot appear twice.
3.6 During `building`, animate items as `complete_trip` creates them. Enable
    **Cancel flight** only after flight/hotel/ground/dining/experience all exist
    in their initial booked state and no local/server disruption state is active.
    Re-enable only for a consent stand-down retry, never after `recovered`.

## 4. Visible cancellation and Vocal Bridge consent call

4.1 Add an endpoint-specific `APIService.demoDisrupt` request path with a timeout
    comfortably above the observed 10–16-second Vocal Bridge queue time; decode
    `DemoDisruptResponse` rather than discarding it.
4.2 On **Cancel flight**, atomically guard against repeat taps, preserve the
    transcript, disconnect the WebRTC voice session, enter `dialing`, then POST
    the active `trip_id`. Do not mark any item broken locally.
4.3 Reconcile completion from both channels: a successful response records the
    scrubbed call status; the status poll remains authoritative for the break and
    consent state. On a client timeout/network ambiguity, do not auto-retry—keep
    polling for evidence the server accepted it before offering manual retry.
4.4 Decode and render `awaiting_consent`, `declined`, `timed_out`, and `error`
    from the status payload. Show no recovery clock during the wait. A stand-down
    keeps the broken flight honest and re-enables the visible action for a new
    Call 1 attempt.
4.5 Disable in-app voice reconnection while dialing, awaiting consent, or
    repairing. Approval remains phone-only; add no native approve/repair control.

## 5. Live repair and results presentation

5.1 Fix the native timer semantics: do not start on `broken`; start on the first
    observed `repairing` state after consent, and freeze when no item remains
    broken/repairing. Reset it only for **New trip** or a fresh disruption cycle.
5.2 Animate every item from server statuses (`broken → repairing → fixed`) with
    semantic icon/text plus restrained lifecycle color and Reduce Motion
    fallbacks. Preserve the last good payload during a failed poll.
5.3 Upgrade the flight card to render the server-written replacement fields:
    carrier/flight number, PT times, fare, cabin, duration, stops/layovers, and
    next-day arrival. After repair, render `detail.rebooked_from` as the subdued,
    struck-through prior-flight line.
5.4 When all work settles, show the frozen elapsed time, clear all active repair
    animation, and say “Watch for your summary call.” Do not claim Call 2 was
    answered because its delivery status is not in the iOS contract.
5.5 Observe app `scenePhase` and audio interruption state. Returning active after
    either phone call performs an immediate poll before restarting the cadence;
    never auto-reconnect the in-app voice session after a call interruption.

## 6. Native polish, resilience, and accessibility

6.1 Apply the calm native design system: system backgrounds/materials, SF
    Symbols, indigo accent, generous card spacing, and a bottom safe-area action.
    Reserve strong red/orange/green for lifecycle changes; do not port dashboard
    side panels or desktop density.
6.2 Add short state-specific copy and non-secret error treatment. A 401 preserves
    the existing access-code reset. A poll error keeps the last trip visible with
    a reconnecting label; a failed disrupt never looks like a successful call.
6.3 Add VoiceOver labels, values, and hints for the orb, tab bar, New trip,
    Cancel flight, timer, and each itinerary status. Verify Dynamic Type,
    contrast, Reduce Motion, and non-color status cues.
6.4 Add restrained iOS 17 sensory feedback for trip adoption, disruption, item
    repair, and all-clear, disabled automatically with relevant system settings.
6.5 Recheck `APIConfig.swift` against the deployed Cloud Run service and preserve
    the access gate, privacy manifest, legal/support links, AI-consent flow,
    Keychain lifecycle, and About withdrawal behavior.
6.6 Correct both Debug and Release `LSApplicationCategoryType` build settings from
    `public.app-category.business` to `public.app-category.travel` before the next
    archive. App Store Connect already uses Travel; the bundle metadata must agree.

## 7. Tests, build, and device rehearsal

7.1 Add a `TalkToMyTripTests` XCTest target (no third-party test dependency) and
    inject `URLSession`/clock seams where needed. Cover decoding, lifecycle state,
    clean-slate adoption, Cancel eligibility, timer semantics, retry ambiguity,
    and Pacific formatting with fixtures matching the deployed status contract.
7.2 Compile the app and tests for a generic iOS Simulator with code signing off;
    run the XCTest target on an available iPhone simulator. The existing Home
    screen must build and its no-trip/timeline previews must remain valid after
    manager injection.
7.3 Run a zero-quota rehearsal first: access/consent, both tabs, clean-slate voice
    booking, five-card materialization, status decoding, New trip, offline/resume,
    Dynamic Type, VoiceOver, and tab-switch audio teardown.
7.4 On a physical iPhone against the deployed backend, run the complete yes-path:
    book → Cancel flight → receive/answer yes on Call 1 → return to the app →
    observe live repairs/timer/rebooked flight → receive Call 2. One run consumes
    two outbound calls; record the trip ID, call results, repair duration, and
    any UI recovery after backgrounding.
7.5 Run one controlled no/ambiguous path: Call 1 stands down, no item reaches
    repairing/fixed, no timer or Call 2 occurs, and the visible action permits a
    deliberate retry. This consumes one outbound call.
7.6 Install directly from Xcode only. Do not archive, upload, replace, or submit
    an App Store binary under this feature while Phase 36 is recovering v1.0 (3)
    unchanged. A later unlisted App Store update remains an explicit release
    action with the Phase 20 prerequisite.
