//
//  DemoLifecycleStateTests.swift
//  TalkToMyTripTests
//
//  The requirements' state/eligibility table, asserted row by row against
//  the one pure derivation.
//

import XCTest
@testable import TalkToMyTrip

final class DemoLifecycleStateTests: XCTestCase {

    private func derive(
        hasTrip: Bool = true,
        disruptActive: Bool = false,
        pollFailed: Bool = false,
        items: [ItineraryItem] = [],
        consent: String? = nil
    ) -> DemoLifecycleState {
        deriveDemoLifecycleState(DemoLifecycleInput(
            hasActiveDemoTrip: hasTrip,
            disruptRequestActive: disruptActive,
            pollFailed: pollFailed,
            items: items,
            consentState: consent
        ))
    }

    func testNoActiveTripIsBooking() {
        XCTAssertEqual(derive(hasTrip: false), .booking)
        // Even stale inputs can't override a missing trip.
        XCTAssertEqual(
            derive(hasTrip: false, items: makeLegs(status: "booked")), .booking
        )
    }

    func testPartialLegsIsBuilding() {
        let partial = [
            makeItem(id: "i1", type: "flight", status: "booked"),
            makeItem(id: "i2", type: "hotel", status: "booked"),
        ]
        XCTAssertEqual(derive(items: partial), .building)
        XCTAssertFalse(derive(items: partial).allowsCancel)

        // All five types present but one still planned → not ready yet.
        var legs = makeLegs(status: "booked")
        legs[4] = makeItem(id: "item-4", type: "experience", status: "planned")
        XCTAssertEqual(derive(items: legs), .building)
    }

    func testCompleteBookedTripIsReadyAndCancelArms() {
        let state = derive(items: makeLegs(status: "booked"))
        XCTAssertEqual(state, .ready)
        XCTAssertTrue(state.allowsCancel)
        XCTAssertTrue(state.allowsNewTrip)
        XCTAssertTrue(state.allowsVoiceConnect)
    }

    func testLocalDisruptRequestIsDialingWithoutItemMutation() {
        // The items are still every bit booked — dialing is purely local.
        let state = derive(disruptActive: true, items: makeLegs(status: "booked"))
        XCTAssertEqual(state, .dialing)
        XCTAssertFalse(state.allowsCancel)
        XCTAssertFalse(state.allowsNewTrip)
        XCTAssertFalse(state.allowsVoiceConnect)
    }

    func testBrokenAwaitingConsentIsAwaitingWithEverythingDisabled() {
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        let state = derive(items: legs, consent: "awaiting_consent")
        XCTAssertEqual(state, .awaitingConsent)
        XCTAssertFalse(state.allowsCancel)
        XCTAssertFalse(state.allowsNewTrip)
        XCTAssertFalse(state.allowsVoiceConnect)
    }

    func testStandDownStatesPermitExplicitRetry() {
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        for consent in ["declined", "timed_out", "error"] {
            let state = derive(items: legs, consent: consent)
            XCTAssertEqual(state, .standingDown, "consent=\(consent)")
            XCTAssertTrue(state.allowsCancel, "retry after \(consent)")
            XCTAssertTrue(state.allowsNewTrip)
        }
    }

    func testRepairingAfterConsent() {
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "repairing")
        let state = derive(items: legs, consent: "granted")
        XCTAssertEqual(state, .repairing)
        XCTAssertFalse(state.allowsCancel)
        XCTAssertFalse(state.allowsVoiceConnect)

        // Granted but the first repairing flip hasn't landed yet — same
        // beat, never a bounce back to the waiting treatment.
        var broken = makeLegs(status: "booked")
        broken[0] = makeItem(id: "item-0", type: "flight", status: "broken")
        XCTAssertEqual(derive(items: broken, consent: "granted"), .repairing)
    }

    func testRecoveredWhenNothingActiveAndSomethingFixed() {
        var legs = makeLegs(status: "booked")
        legs[0] = makeItem(id: "item-0", type: "flight", status: "fixed")
        let state = derive(items: legs, consent: "granted")
        XCTAssertEqual(state, .recovered)
        // Never re-arm Cancel after a successful recovery — New trip is the
        // next full run.
        XCTAssertFalse(state.allowsCancel)
        XCTAssertTrue(state.allowsNewTrip)
    }

    func testPollFailureIsReconnectingNotCleared() {
        let state = derive(pollFailed: true, items: makeLegs(status: "booked"))
        XCTAssertEqual(state, .reconnecting)
        XCTAssertFalse(state.allowsCancel)
    }
}
