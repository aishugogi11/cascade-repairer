//
//  DemoFlowManager.swift
//  TalkToMyTrip
//
//  The Demo tab's flow: clean-slate booking baseline, adoption of the newly
//  booked trip, the 1.5-second status poll, the visible Cancel flight
//  disrupt request, and the repair timer. Server truth over optimistic
//  animation — the poll is authoritative for every break, consent, and
//  repair state; this manager never mutates an item locally and never
//  starts a repair.
//

import Foundation
import Observation

/// How a local disrupt request stands relative to server evidence.
enum DisruptRequestPhase: Equatable {
    case idle
    /// The POST is in flight.
    case requesting
    /// The POST returned 200 — the call is queued; waiting for the poll to
    /// show the break (the server stays authoritative).
    case accepted
    /// The POST failed ambiguously (timeout / network) — the server may
    /// already have queued a quota-consuming call, so no automatic retry;
    /// polls reconcile before manual retry is offered.
    case ambiguous(pollsSinceFailure: Int)
}

@Observable @MainActor
final class DemoFlowManager {
    // MARK: - Observable state

    var trip: Trip?
    var items: [ItineraryItem] = []
    var summary: StatusSummary?
    var consent: ConsentStatus?
    /// True while the last poll failed after a trip was known — the last
    /// good payload stays on screen.
    var pollFailed = false
    /// Item ids whose status changed in the last poll — cards animate on it.
    var changedItemIDs: Set<String> = []
    /// Running repair clock: anchored at the FIRST observed repairing state
    /// after consent — never at broken (the wait shows no clock).
    var repairStartedAt: Date?
    /// Frozen elapsed seconds once no item remains broken/repairing.
    var repairElapsed: TimeInterval?
    /// Scrubbed call status from a successful disrupt response ("queued").
    var lastCallStatus: String?
    /// Friendly, non-secret error copy for a failed disrupt.
    var disruptError: String?
    private(set) var disruptPhase: DisruptRequestPhase = .idle

    private(set) var activeTripID: String?

    // MARK: - Wiring (set by the shell)

    /// The demo pin changed — forward to the voice page (nil clears it).
    var onTripPinChanged: (String?) -> Void = { _ in }
    /// Cancel flight must end the in-app voice session first — but the
    /// transcript stays on screen.
    var onVoiceDisconnectNeeded: () -> Void = {}
    /// New trip ends the session AND clears the shared transcript.
    var onNewTripReset: () -> Void = {}

    // MARK: - Seams (injectable for tests)

    private let api: DemoBackend
    private let store: DemoSessionStore
    private let now: () -> Date

    private var baselineCaptured = false
    private var needsTripRefresh = false
    private var previousStatuses: [String: String] = [:]
    private var pollTask: Task<Void, Never>?
    private var pollingPaused = false

    init(
        api: DemoBackend = APIService.shared,
        store: DemoSessionStore = DemoSessionStore(),
        now: @escaping () -> Date = Date.init
    ) {
        self.api = api
        self.store = store
        self.now = now
    }

    // MARK: - Derived state

    var lifecycleState: DemoLifecycleState {
        deriveDemoLifecycleState(DemoLifecycleInput(
            hasActiveDemoTrip: activeTripID != nil,
            disruptRequestActive: disruptRequestActive,
            pollFailed: pollFailed && trip != nil,
            items: items,
            consentState: consent?.state
        ))
    }

    private var disruptRequestActive: Bool {
        switch disruptPhase {
        case .requesting, .accepted: return true
        case .ambiguous: return true
        case .idle: return false
        }
    }

    /// Manual retry after an ambiguous failure only once the polls have
    /// settled with no server evidence of the break.
    private static let ambiguousSettlePolls = 3

    // MARK: - Lifecycle

    func start() {
        // A persisted demo trip means an interrupted run (phone call,
        // relaunch): resume it — do NOT baseline it away as a new trip.
        if let persisted = store.activeDemoTripID {
            activeTripID = persisted
            baselineCaptured = true
            onTripPinChanged(persisted)
        }
        resumePolling()
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
    }

    func pausePolling() {
        pollingPaused = true
    }

    func resumePolling() {
        pollingPaused = false
        guard pollTask == nil else { return }
        pollTask = Task { await pollLoop() }
    }

    /// scenePhase turned active (possibly returning from Call 1/2) — poll
    /// immediately before the normal cadence resumes.
    func pollNow() {
        Task { await tick() }
    }

    /// The agent replied — it may have just booked the trip; check the
    /// latest id on the next tick.
    func noteAgentReply() {
        needsTripRefresh = true
    }

    // MARK: - New trip

    /// Ends the live voice session, clears this run's local state, captures
    /// a fresh baseline, and returns to booking. The old server-side trip is
    /// never deleted or mutated.
    func newTrip() {
        guard lifecycleState.allowsNewTrip else { return }
        onNewTripReset()
        store.activeDemoTripID = nil
        activeTripID = nil
        trip = nil
        items = []
        summary = nil
        consent = nil
        pollFailed = false
        changedItemIDs = []
        previousStatuses = [:]
        repairStartedAt = nil
        repairElapsed = nil
        lastCallStatus = nil
        disruptError = nil
        disruptPhase = .idle
        baselineCaptured = false
        needsTripRefresh = false
        onTripPinChanged(nil)
        Task { await captureBaselineIfNeeded() }
    }

    // MARK: - Cancel flight (Call 1 trigger)

    /// One tap: guard repeats, keep the transcript, end the in-app voice
    /// session (the inbound phone call needs the audio route), then POST.
    /// No item is marked broken locally — the poll reports the break.
    func cancelFlight() async {
        guard lifecycleState.allowsCancel, let tripID = activeTripID else { return }
        disruptError = nil
        disruptPhase = .requesting
        onVoiceDisconnectNeeded()
        do {
            let response = try await api.demoDisrupt(tripID: tripID)
            lastCallStatus = response.call_status
            disruptPhase = .accepted
        } catch let APIError.server(message, _) {
            // A definitive HTTP error: the backend rejected it and said why
            // (scrubbed). Safe to re-arm the action.
            disruptError = friendlyDisruptError(message)
            disruptPhase = .idle
        } catch APIError.unauthorized {
            disruptPhase = .idle
        } catch {
            // Timeout or network ambiguity — the server may have accepted
            // it. Keep polling for evidence; never auto-POST again.
            disruptPhase = .ambiguous(pollsSinceFailure: 0)
        }
    }

    /// The backend's messages are already scrubbed, but keep the copy human
    /// and never pass through anything that looks like a payload dump.
    private func friendlyDisruptError(_ message: String) -> String {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 200, !trimmed.contains("{") else {
            return "The cancellation call couldn't be placed. Your trip is unchanged — try again."
        }
        return "The cancellation call couldn't be placed: \(trimmed). Your trip is unchanged."
    }

    // MARK: - Polling

    private func pollLoop() async {
        while !Task.isCancelled {
            if !pollingPaused {
                await tick()
            }
            try? await Task.sleep(for: .seconds(1.5))
        }
    }

    /// Internal (not private) so tests can drive one deterministic cycle.
    func tick() async {
        await captureBaselineIfNeeded()
        if activeTripID == nil || needsTripRefresh {
            needsTripRefresh = false
            await adoptNewTripIfAny()
        }
        guard let tripID = activeTripID else { return }

        do {
            let status = try await api.status(tripID: tripID)
            apply(status)
        } catch APIError.unauthorized {
            // Heading back to the gate — stop rather than spamming 401s.
            stop()
        } catch {
            // Keep the last good payload; the loop recovers on its own.
            pollFailed = true
        }
    }

    /// First run / after New trip: remember the backend's current latest
    /// trip so it is never displayed — only a DIFFERENT id gets adopted.
    private func captureBaselineIfNeeded() async {
        guard !baselineCaptured else { return }
        do {
            // nil is a valid baseline — a backend with no trips at all.
            store.baselineTripID = try await api.latestTripID()
            baselineCaptured = true
        } catch {
            // Unreachable — leave the flag unset so the next tick retries.
        }
    }

    private func adoptNewTripIfAny() async {
        guard baselineCaptured, activeTripID == nil else { return }
        guard let latest = try? await api.latestTripID(), !latest.isEmpty,
              latest != store.baselineTripID else { return }
        activeTripID = latest
        store.activeDemoTripID = latest
        previousStatuses = [:]
        onTripPinChanged(latest)
    }

    /// Whether the 1.5-second loop is alive — asserted by the 401 tests.
    var isPolling: Bool { pollTask != nil }

    /// Internal (not private) so tests can feed poll payloads directly.
    func apply(_ status: TripStatusResponse) {
        // A successfully applied payload IS a successful poll.
        pollFailed = false
        var changed: Set<String> = []
        for item in status.items {
            if let previous = previousStatuses[item.item_id], previous != item.status {
                changed.insert(item.item_id)
            }
        }
        changedItemIDs = changed
        previousStatuses = Dictionary(
            uniqueKeysWithValues: status.items.map { ($0.item_id, $0.status) }
        )

        trip = status.trip
        items = status.items
        summary = status.summary
        consent = status.consent

        reconcileDisruptPhase(with: status)
        updateRepairTimer(with: status)
    }

    /// The poll is authoritative: server evidence of the break (broken item
    /// or a consent block) closes the local request phase — including an
    /// ambiguous timeout, which then counts as accepted. An ambiguous
    /// failure with no evidence after the settle window re-arms Cancel.
    private func reconcileDisruptPhase(with status: TripStatusResponse) {
        let serverSawIt = status.items.contains { $0.status == "broken" }
            || status.consent != nil
        switch disruptPhase {
        case .accepted where serverSawIt:
            disruptPhase = .idle
        case .ambiguous where serverSawIt:
            disruptPhase = .idle
        case .ambiguous(let polls):
            if polls + 1 >= Self.ambiguousSettlePolls {
                disruptPhase = .idle
                disruptError = "We couldn't confirm the cancellation call went out. Your trip looks unchanged — you can try again."
            } else {
                disruptPhase = .ambiguous(pollsSinceFailure: polls + 1)
            }
        default:
            break
        }
    }

    /// Timer semantics: broken/awaiting never start it; the FIRST observed
    /// repairing state after consent does. It freezes when nothing remains
    /// broken/repairing, and only New trip or a fresh disruption cycle
    /// resets it. A failed poll never touches it (this runs on success only).
    private func updateRepairTimer(with status: TripStatusResponse) {
        let statuses = status.items.map(\.status)
        let anyRepairing = statuses.contains("repairing")
        let anyActive = anyRepairing || statuses.contains("broken")

        if repairStartedAt == nil, repairElapsed == nil, anyRepairing {
            repairStartedAt = now()
        } else if let started = repairStartedAt, !anyActive {
            repairElapsed = now().timeIntervalSince(started)
            repairStartedAt = nil
        }

        // A fresh disruption cycle (new break after a completed run) clears
        // the frozen reading so the next repair times itself.
        if repairElapsed != nil, statuses.contains("broken") {
            repairElapsed = nil
        }
    }
}
