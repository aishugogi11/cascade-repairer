//
//  PacificFormatTests.swift
//  TalkToMyTripTests
//
//  UTC fixtures render America/Los_Angeles with the PT label regardless of
//  the simulator's timezone; missing facts return nil so views omit them
//  and their separators cleanly.
//

import XCTest
@testable import TalkToMyTrip

final class PacificFormatTests: XCTestCase {

    func testUTCTimestampRendersPacificWithPTLabel() {
        // 15:05 UTC on a July date is 8:05 AM PDT.
        XCTAssertEqual(
            PacificFormat.time(fromISO: "2026-07-21T15:05:00+00:00"),
            "8:05 AM PT"
        )
        // Zulu suffix and the backend's microsecond fractions both parse.
        XCTAssertEqual(
            PacificFormat.time(fromISO: "2026-07-21T15:05:00Z"),
            "8:05 AM PT"
        )
        XCTAssertEqual(
            PacificFormat.time(fromISO: "2026-07-21T15:05:00.123456+00:00"),
            "8:05 AM PT"
        )
    }

    func testWinterTimestampStillSaysPTNotPST() {
        // January is PST (UTC-8) — the label stays the standing "PT".
        XCTAssertEqual(
            PacificFormat.time(fromISO: "2026-01-21T16:05:00+00:00"),
            "8:05 AM PT"
        )
    }

    func testTimeRangeDegradesToWhicheverEndExists() {
        XCTAssertEqual(
            PacificFormat.timeRange(
                departISO: "2026-07-21T15:05:00+00:00",
                arriveISO: "2026-07-21T21:32:00+00:00"
            ),
            "8:05 AM → 2:32 PM PT"
        )
        XCTAssertEqual(
            PacificFormat.timeRange(departISO: "2026-07-21T15:05:00+00:00", arriveISO: nil),
            "8:05 AM PT"
        )
        XCTAssertNil(PacificFormat.timeRange(departISO: nil, arriveISO: nil))
    }

    func testMissingOrUnparseableTimestampsReturnNil() {
        XCTAssertNil(PacificFormat.time(fromISO: nil))
        XCTAssertNil(PacificFormat.time(fromISO: ""))
        XCTAssertNil(PacificFormat.time(fromISO: "not-a-date"))
    }

    func testDurationOmitsUnknownAndFormatsCleanly() {
        XCTAssertNil(PacificFormat.duration(minutes: nil))
        XCTAssertNil(PacificFormat.duration(minutes: 0), "0 is the backend's unknown")
        XCTAssertEqual(PacificFormat.duration(minutes: 45), "45m")
        XCTAssertEqual(PacificFormat.duration(minutes: 120), "2h")
        XCTAssertEqual(PacificFormat.duration(minutes: 327), "5h 27m")
    }

    func testFareFormatsUSDAndOmitsMissing() {
        XCTAssertNil(PacificFormat.fare(price: nil, currency: "USD"))
        XCTAssertEqual(PacificFormat.fare(price: 385.0, currency: "USD"), "$385")
        XCTAssertEqual(PacificFormat.fare(price: 385.6, currency: "USD"), "$386")
        XCTAssertEqual(PacificFormat.fare(price: 240.0, currency: nil), "$240")
        XCTAssertEqual(PacificFormat.fare(price: 300.0, currency: "EUR"), "300 EUR")
    }

    func testStopsLineCoversNonstopSingularPluralAndUnknown() {
        XCTAssertNil(PacificFormat.stops(count: nil, layovers: nil), "pre-Phase-33 rows say nothing")
        XCTAssertEqual(PacificFormat.stops(count: 0, layovers: []), "Nonstop")
        XCTAssertEqual(PacificFormat.stops(count: 1, layovers: ["DEN"]), "1 stop via DEN")
        XCTAssertEqual(PacificFormat.stops(count: 2, layovers: ["DEN", "ORD"]), "2 stops via DEN, ORD")
        XCTAssertEqual(PacificFormat.stops(count: 1, layovers: nil), "1 stop")
    }
}
