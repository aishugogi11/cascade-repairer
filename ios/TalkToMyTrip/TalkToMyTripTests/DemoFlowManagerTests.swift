//
//  DemoFlowManagerTests.swift
//  TalkToMyTripTests
//
//  Clean-slate adoption, Cancel guards, disrupt reconciliation, timer
//  semantics, and the 401 stop — driven deterministically through the
//  manager's tick/apply seams with a fake backend and injected clock.
//

import XCTest
@testable import TalkToMyTrip

@MainActor
final class DemoFlowManagerTests: XCTestCase {

    // MARK: - Clean slate and adoption

    func testBaselineIsCapturedButNeverDisplayedOrPinned() async {
        let api = FakeBackend()
        api.latestTripIDResult = .success("old-trip")
        let (manager, store) = makeManager(api: api)
        var pins: [String?] = []
        manager.onTripPinChanged = { pins.append($0) }

        await manager.tick()

        XCTAssertEqual(store.baselineTripID, "old-trip")
        XCTAssertNil(manager.activeTripID)
        XCTAssertNil(store.activeDemoTripID)
        XCTAssertEqual(manager.lifecycleState, .booking)
        XCTAssertTrue(pins.isEmpty, "the baseline must never reach the voice page")
        XCTAssertEqual(api.statusCalls, 0, "the baseline trip is never polled")
    }

    func testSameLatestIDDoesNothingChangedIDAdoptedOnce() async {
        let api = FakeBackend()
        api.latestTripIDResult = .success("old-trip")
        let (manager, store) = makeManager(api: api)
        var pins: [String?] = []
        manager.onTripPinChanged = { pins.append($0) }

        await manager.tick()  // captures baseline; same id → no adoption
        XCTAssertNil(manager.activeTripID)

        api.latestTripIDResult = .success("new-trip")
        api.statusResult = .success(makeStatus(tripID: "new-trip", items: makeLegs(status: "booked")))
        await manager.tick()

        XCTAssertEqual(manager.activeTripID, "new-trip")
        XCTAssertEqual(store.activeDemoTripID, "new-trip", "persisted for resume")
        XCTAssertEqual(pins, ["new-trip"])

        // Re-reading the same id adopts nothing twice and re-pins nothing.
        await manager.tick()
        XCTAssertEqual(pins, ["new-trip"])
        XCTAssertEqual(manager.activeTripID, "new-trip")
    }

    func testPersistedDemoTripResumesInsteadOfBaseliningAway() async {
        let api = FakeBackend()
        api.latestTripIDResult = .success("resume-trip")
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        api.statusResult = .success(makeStatus(
            tripID: "resume-trip", items: legs,
            consent: makeConsent("awaiting_consent")
        ))
        let defaults = UserDefaults(suiteName: "test-\(UUID().uuidString)")!
        let store = DemoSessionStore(defaults: defaults)
        store.activeDemoTripID = "resume-trip"
        let (manager, _) = makeManager(api: api, store: store)
        var pins: [String?] = []
        manager.onTripPinChanged = { pins.append($0) }

        manager.start()
        manager.stop()
        XCTAssertEqual(manager.activeTripID, "resume-trip")
        XCTAssertEqual(pins, ["resume-trip"])

        await manager.tick()
        XCTAssertEqual(manager.lifecycleState, .awaitingConsent)
        XCTAssertNil(manager.repairStartedAt, "no clock while awaiting consent")
    }

    func testNewTripClearsRunAndCapturesFreshBaseline() async {
        let api = FakeBackend()
        api.latestTripIDResult = .success("old-trip")
        let (manager, store) = makeManager(api: api)
        await manager.tick()

        api.latestTripIDResult = .success("demo-trip")
        api.statusResult = .success(makeStatus(tripID: "demo-trip", items: makeLegs(status: "booked")))
        await manager.tick()
        XCTAssertEqual(manager.activeTripID, "demo-trip")

        var resetCalls = 0
        var pins: [String?] = []
        manager.onNewTripReset = { resetCalls += 1 }
        manager.onTripPinChanged = { pins.append($0) }

        manager.newTrip()

        XCTAssertEqual(resetCalls, 1, "voice ends and transcript clears")
        XCTAssertEqual(pins, [nil], "the page pin is cleared")
        XCTAssertNil(manager.activeTripID)
        XCTAssertNil(store.activeDemoTripID)
        XCTAssertNil(manager.trip)
        XCTAssertTrue(manager.items.isEmpty)
        XCTAssertNil(manager.repairStartedAt)
        XCTAssertNil(manager.repairElapsed)
        XCTAssertEqual(manager.lifecycleState, .booking)
        XCTAssertEqual(api.disruptCalls, 0, "New trip never mutates the server")

        // The old demo trip is now the baseline — it is never re-adopted.
        await manager.tick()
        XCTAssertEqual(store.baselineTripID, "demo-trip")
        XCTAssertNil(manager.activeTripID)
    }

    func testNewTripUnavailableDuringConsentWait() async {
        let api = FakeBackend()
        let manager = await adoptedManager(api: api)
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        manager.apply(makeStatus(items: legs, consent: makeConsent("awaiting_consent")))

        var resetCalls = 0
        manager.onNewTripReset = { resetCalls += 1 }
        manager.newTrip()

        XCTAssertEqual(resetCalls, 0)
        XCTAssertNotNil(manager.activeTripID, "the run survives")
    }

    // MARK: - Cancel flight

    func testCancelIneligibleSendsNoRequest() async {
        let api = FakeBackend()
        let manager = await adoptedManager(api: api)
        // Building: hotel still planned.
        var legs = makeLegs(status: "booked")
        legs[1] = makeItem(id: "item-1", type: "hotel", status: "planned")
        manager.apply(makeStatus(items: legs))

        await manager.cancelFlight()
        XCTAssertEqual(api.disruptCalls, 0)
    }

    func testCancelFlightDisconnectsVoiceDialsAndNeverMutatesItems() async {
        let api = FakeBackend()
        api.disruptResult = .success(DemoDisruptResponse(
            trip_id: "demo-trip", item_id: "i1", call_id: "call-1",
            call_status: "queued", consent: "awaiting_consent"
        ))
        let manager = await adoptedManager(api: api)
        manager.apply(makeStatus(items: makeLegs(status: "booked")))
        XCTAssertEqual(manager.lifecycleState, .ready)

        var disconnects = 0
        manager.onVoiceDisconnectNeeded = { disconnects += 1 }

        await manager.cancelFlight()

        XCTAssertEqual(disconnects, 1, "voice ends before the POST")
        XCTAssertEqual(api.disruptCalls, 1)
        XCTAssertEqual(manager.lastCallStatus, "queued")
        XCTAssertEqual(manager.lifecycleState, .dialing)
        XCTAssertTrue(
            manager.items.allSatisfy { $0.status == "booked" },
            "no optimistic local break"
        )

        // Repeat tap while dialing: guarded, no second call.
        await manager.cancelFlight()
        XCTAssertEqual(api.disruptCalls, 1)

        // The poll reports the break — server truth takes over.
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        manager.apply(makeStatus(items: legs, consent: makeConsent("awaiting_consent")))
        XCTAssertEqual(manager.lifecycleState, .awaitingConsent)
    }

    func testAmbiguousTimeoutNeverAutoRetriesAndSettlesToManualRetry() async {
        let api = FakeBackend()
        api.disruptResult = .failure(URLError(.timedOut))
        let manager = await adoptedManager(api: api)
        let ready = makeStatus(items: makeLegs(status: "booked"))
        manager.apply(ready)

        await manager.cancelFlight()
        XCTAssertEqual(api.disruptCalls, 1)
        XCTAssertEqual(manager.lifecycleState, .dialing, "ambiguity is not a failure claim")
        XCTAssertFalse(manager.lifecycleState.allowsCancel)

        // Polls settle with no server evidence → the request is treated as
        // not accepted; manual retry re-arms. Never an automatic POST.
        manager.apply(ready)
        manager.apply(ready)
        manager.apply(ready)
        XCTAssertEqual(api.disruptCalls, 1)
        XCTAssertEqual(manager.lifecycleState, .ready)
        XCTAssertNotNil(manager.disruptError)
    }

    func testAmbiguousTimeoutWithServerEvidenceCountsAsAccepted() async {
        let api = FakeBackend()
        api.disruptResult = .failure(URLError(.networkConnectionLost))
        let manager = await adoptedManager(api: api)
        manager.apply(makeStatus(items: makeLegs(status: "booked")))

        await manager.cancelFlight()
        XCTAssertEqual(manager.lifecycleState, .dialing)

        // The server did accept it: broken + consent arrive on the poll.
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        manager.apply(makeStatus(items: legs, consent: makeConsent("awaiting_consent")))

        XCTAssertEqual(manager.lifecycleState, .awaitingConsent)
        XCTAssertNil(manager.disruptError, "an accepted call is not an error")
        XCTAssertEqual(api.disruptCalls, 1)
    }

    func testServerErrorShowsFriendlyScrubbedCopyAndRearms() async {
        let api = FakeBackend()
        api.disruptResult = .failure(APIError.server(message: "VB call failed", status: 502))
        let manager = await adoptedManager(api: api)
        manager.apply(makeStatus(items: makeLegs(status: "booked")))

        await manager.cancelFlight()

        let message = try? XCTUnwrap(manager.disruptError)
        XCTAssertTrue(message?.contains("VB call failed") == true)
        XCTAssertEqual(manager.lifecycleState, .ready, "a definitive failure re-arms")
        XCTAssertTrue(manager.items.allSatisfy { $0.status == "booked" })
    }

    func testRawLookingServerMessageIsNeverEchoed() async {
        let api = FakeBackend()
        api.disruptResult = .failure(APIError.server(
            message: #"{"callee": "+15551234567", "api_key": "sk-secret"}"#, status: 502
        ))
        let manager = await adoptedManager(api: api)
        manager.apply(makeStatus(items: makeLegs(status: "booked")))

        await manager.cancelFlight()

        let message = manager.disruptError ?? ""
        XCTAssertFalse(message.contains("{"), "no payload dumps in UI copy")
        XCTAssertFalse(message.contains("+1555"))
        XCTAssertFalse(message.contains("sk-secret"))
        XCTAssertFalse(message.isEmpty)
    }

    // MARK: - Timer semantics

    func testBrokenAndAwaitingConsentNeverStartTheTimer() async {
        let api = FakeBackend()
        let manager = await adoptedManager(api: api)
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")

        manager.apply(makeStatus(items: legs))
        XCTAssertNil(manager.repairStartedAt)

        manager.apply(makeStatus(items: legs, consent: makeConsent("awaiting_consent")))
        XCTAssertNil(manager.repairStartedAt)
        XCTAssertNil(manager.repairElapsed)
    }

    func testTimerStartsOnFirstRepairingFreezesOnSettleAndSurvivesPollFailure() async {
        var currentTime = Date(timeIntervalSince1970: 1_000_000)
        let api = FakeBackend()
        let manager = await adoptedManager(api: api, now: { currentTime })

        // First repairing after consent → anchored now.
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "repairing")
        manager.apply(makeStatus(items: legs, consent: makeConsent("granted")))
        XCTAssertEqual(manager.repairStartedAt, currentTime)

        // A failed poll preserves the anchor and the last good payload.
        api.statusResult = .failure(FakeBackendError.network)
        await manager.tick()
        XCTAssertTrue(manager.pollFailed)
        XCTAssertEqual(manager.lifecycleState, .reconnecting)
        XCTAssertEqual(manager.repairStartedAt, Date(timeIntervalSince1970: 1_000_000))
        XCTAssertFalse(manager.items.isEmpty, "last good payload survives")

        // Everything settles 42 seconds in → frozen reading.
        currentTime = currentTime.addingTimeInterval(42)
        var fixed = makeLegs(status: "fixed")
        fixed[1] = makeItem(id: "item-1", type: "hotel", status: "booked")
        manager.apply(makeStatus(items: fixed, consent: makeConsent("granted")))
        XCTAssertNil(manager.repairStartedAt)
        XCTAssertEqual(manager.repairElapsed, 42)
        XCTAssertEqual(manager.lifecycleState, .recovered)

        // A later poll with the same settled trip does not restart it.
        manager.apply(makeStatus(items: fixed, consent: makeConsent("granted")))
        XCTAssertEqual(manager.repairElapsed, 42)

        // A fresh disruption cycle clears the frozen reading for a new run.
        var rebroken = fixed
        rebroken[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        manager.apply(makeStatus(items: rebroken, consent: makeConsent("awaiting_consent")))
        XCTAssertNil(manager.repairElapsed)
        XCTAssertNil(manager.repairStartedAt, "broken still never starts it")
    }

    // MARK: - 401

    func testUnauthorizedStopsPolling() async {
        let api = FakeBackend()
        let manager = await adoptedManager(api: api)
        manager.resumePolling()
        XCTAssertTrue(manager.isPolling)

        api.statusResult = .failure(APIError.unauthorized)
        await manager.tick()

        XCTAssertFalse(manager.isPolling, "back to the gate, no 401 spam")
    }

    // MARK: - Helpers

    /// A manager that has already adopted "demo-trip" through the real
    /// clean-slate flow.
    private func adoptedManager(
        api: FakeBackend,
        now: @escaping () -> Date = Date.init
    ) async -> DemoFlowManager {
        api.latestTripIDResult = .success("old-trip")
        let (manager, _) = makeManager(api: api, now: now)
        await manager.tick()
        api.latestTripIDResult = .success("demo-trip")
        api.statusResult = .success(makeStatus(tripID: "demo-trip", items: makeLegs(status: "booked")))
        await manager.tick()
        precondition(manager.activeTripID == "demo-trip")
        return manager
    }
}
