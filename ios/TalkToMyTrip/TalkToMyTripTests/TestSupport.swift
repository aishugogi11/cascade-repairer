//
//  TestSupport.swift
//  TalkToMyTripTests
//
//  Shared builders and the fake backend the manager tests drive — no
//  network, no clock, no shared UserDefaults.
//

import Foundation
@testable import TalkToMyTrip

// MARK: - Fake backend

enum FakeBackendError: Error {
    case unstubbed
    case network
}

@MainActor
final class FakeBackend: DemoBackend {
    var latestTripIDResult: Result<String?, Error> = .success(nil)
    var statusResult: Result<TripStatusResponse, Error> = .failure(FakeBackendError.unstubbed)
    var disruptResult: Result<DemoDisruptResponse, Error> = .failure(FakeBackendError.unstubbed)

    private(set) var latestCalls = 0
    private(set) var statusCalls = 0
    private(set) var disruptCalls = 0
    private(set) var statusTripIDs: [String] = []

    func latestTripID() async throws -> String? {
        latestCalls += 1
        return try latestTripIDResult.get()
    }

    func status(tripID: String) async throws -> TripStatusResponse {
        statusCalls += 1
        statusTripIDs.append(tripID)
        return try statusResult.get()
    }

    @discardableResult
    func demoDisrupt(tripID: String) async throws -> DemoDisruptResponse {
        disruptCalls += 1
        return try disruptResult.get()
    }
}

// MARK: - Builders

func makeTrip(id: String = "trip-1") -> Trip {
    Trip(
        trip_id: id, title: "New York to Los Angeles", status: "booked",
        origin: "JFK", destinations: ["LAX"],
        start_date: "2026-07-21", end_date: "2026-07-23"
    )
}

func makeItem(
    id: String,
    type: String,
    status: String,
    detail: ItemDetail? = nil,
    details: FlightDetails? = nil
) -> ItineraryItem {
    ItineraryItem(
        item_id: id, trip_id: "trip-1", type: type, status: status,
        location: "\(type) location", start_ts: nil, end_ts: nil,
        price: 100, currency: "USD", detail: detail, details: details
    )
}

/// The five-leg itinerary in one uniform status.
func makeLegs(status: String) -> [ItineraryItem] {
    ["flight", "hotel", "ground", "dining", "experience"].enumerated().map {
        makeItem(id: "item-\($0.offset)", type: $0.element, status: status)
    }
}

func makeStatus(
    tripID: String = "trip-1",
    items: [ItineraryItem],
    consent: ConsentStatus? = nil
) -> TripStatusResponse {
    let statuses = items.map(\.status)
    let allClear = !statuses.contains("broken")
        && !statuses.contains("repairing")
        && !statuses.contains("cancelled")
    var counts: [String: Int] = [:]
    for status in statuses { counts[status, default: 0] += 1 }
    return TripStatusResponse(
        trip: makeTrip(id: tripID),
        items: items,
        summary: StatusSummary(counts: counts, all_clear: allClear),
        fetched_at: "2026-07-16T20:00:00+00:00",
        consent: consent
    )
}

func makeConsent(_ state: String, message: String? = nil) -> ConsentStatus {
    ConsentStatus(
        state: state,
        message: message ?? "consent \(state) message",
        since: "2026-07-16T20:00:00+00:00",
        updated_at: "2026-07-16T20:00:05+00:00"
    )
}

// MARK: - Manager factory

@MainActor
func makeManager(
    api: FakeBackend,
    store: DemoSessionStore? = nil,
    now: @escaping () -> Date = Date.init
) -> (DemoFlowManager, DemoSessionStore) {
    let defaults = UserDefaults(suiteName: "test-\(UUID().uuidString)")!
    let sessionStore = store ?? DemoSessionStore(defaults: defaults)
    let manager = DemoFlowManager(api: api, store: sessionStore, now: now)
    return (manager, sessionStore)
}
