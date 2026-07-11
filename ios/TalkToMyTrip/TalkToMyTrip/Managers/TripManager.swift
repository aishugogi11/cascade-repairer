//
//  TripManager.swift
//  TalkToMyTrip
//
//  Polls trip status every 1.5s (the same contract the web itinerary page
//  uses), re-resolves the latest trip on session start and after each agent
//  reply — so a trip booked by voice mid-session appears without an app
//  restart — and diffs item statuses between polls to drive the card
//  animations and the recovery timer.
//

import Foundation
import Observation

@Observable @MainActor
final class TripManager {
    var trip: Trip?
    var items: [ItineraryItem] = []
    var summary: StatusSummary?
    /// Item ids whose status changed in the last poll — cards pulse on it.
    var changedItemIDs: Set<String> = []
    /// True while the last poll failed (airplane mode etc.) — the loop
    /// keeps running and recovers on its own.
    var pollFailed = false
    /// Running since the first broken item; nil when not disrupted.
    var recoveryStartedAt: Date?
    /// Final elapsed seconds once the trip is all-clear again.
    var recoveryElapsed: TimeInterval?
    var demoActionInFlight = false

    private(set) var tripID: String?
    private var pollTask: Task<Void, Never>?
    private var needsTripRefresh = true
    private var previousStatuses: [String: String] = [:]

    var repairingCount: Int { summary?.counts["repairing"] ?? 0 }

    var hasBreakableFlight: Bool {
        items.contains { $0.type == "flight" && $0.status != "broken" }
    }

    func start() {
        guard pollTask == nil else { return }
        pollTask = Task { await pollLoop() }
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
    }

    /// Called after each agent reply: the agent may have just booked a new
    /// trip, so the next tick re-resolves the latest trip id.
    func noteAgentReply() {
        needsTripRefresh = true
    }

    // MARK: - Demo controls

    func simulateFlightCancellation() async {
        guard let tripID, !demoActionInFlight else { return }
        demoActionInFlight = true
        defer { demoActionInFlight = false }
        try? await APIService.shared.breakFlight(tripID: tripID)
    }

    /// The reviewer-path fallback — heals the trip without speaking.
    func repairNow() async {
        guard let tripID, !demoActionInFlight else { return }
        demoActionInFlight = true
        defer { demoActionInFlight = false }
        try? await APIService.shared.repairTrip(tripID: tripID)
    }

    // MARK: - Polling

    private func pollLoop() async {
        while !Task.isCancelled {
            await tick()
            try? await Task.sleep(for: .seconds(1.5))
        }
    }

    private func tick() async {
        if needsTripRefresh || tripID == nil {
            if let latest = try? await APIService.shared.latestTripID() {
                needsTripRefresh = false
                if latest != tripID {
                    tripID = latest
                    previousStatuses = [:]
                    recoveryStartedAt = nil
                    recoveryElapsed = nil
                }
            }
        }
        guard let tripID else { return }

        do {
            let status = try await APIService.shared.status(tripID: tripID)
            apply(status)
            pollFailed = false
        } catch {
            pollFailed = true  // keep polling; next success clears it
        }
    }

    private func apply(_ status: TripStatusResponse) {
        var changed: Set<String> = []
        for item in status.items {
            if let previous = previousStatuses[item.item_id],
               previous != item.status {
                changed.insert(item.item_id)
            }
        }
        changedItemIDs = changed
        previousStatuses = Dictionary(
            uniqueKeysWithValues: status.items.map { ($0.item_id, $0.status) }
        )

        // Recovery timer: starts on the first broken item, stops (and keeps
        // its final reading) when everything is clear again.
        let anyDisrupted = !status.summary.all_clear
        if recoveryStartedAt == nil && status.items.contains(where: { $0.status == "broken" }) {
            recoveryStartedAt = Date()
            recoveryElapsed = nil
        } else if let started = recoveryStartedAt, !anyDisrupted {
            recoveryElapsed = Date().timeIntervalSince(started)
            recoveryStartedAt = nil
        }

        trip = status.trip
        items = status.items
        summary = status.summary
    }
}
