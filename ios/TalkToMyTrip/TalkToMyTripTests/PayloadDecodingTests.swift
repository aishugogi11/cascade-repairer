//
//  PayloadDecodingTests.swift
//  TalkToMyTripTests
//
//  The deployed /v1/itinerary/status contract: full rich payloads decode,
//  and every additive block (consent, details, detail, individual rich
//  fields) can be omitted — or arrive misshapen — without failing the poll
//  or producing placeholder copy.
//

import XCTest
@testable import TalkToMyTrip

final class PayloadDecodingTests: XCTestCase {

    /// Deployed-shape fixture: trip + all six lifecycle statuses + summary
    /// + consent + rich flight details + rebooked_from.
    private let fullFixture = """
    {
      "trip": {
        "trip_id": "trip-1", "user_id": "demo", "title": "New York to Los Angeles",
        "status": "booked", "origin": "JFK", "destinations": ["LAX"],
        "start_date": "2026-07-21", "end_date": "2026-07-23",
        "created_at": "2026-07-16T18:00:00+00:00"
      },
      "items": [
        {"item_id": "i1", "trip_id": "trip-1", "type": "flight", "status": "fixed",
         "provider": "sabre", "provider_ref": "ABC123",
         "start_ts": "2026-07-21T15:05:00+00:00", "end_ts": "2026-07-21T21:32:00+00:00",
         "location": "JFK → LAX", "price": 385.0, "currency": "USD",
         "details": {"airline": "AA", "flight_number": "118",
                     "airline_name": "American Airlines", "cabin": "Economy",
                     "duration_minutes": 327, "layover_airports": [],
                     "arrives_next_day": false, "stops": 0},
         "detail": {"why_chosen": "Closest arrival to your original flight.",
                    "price_delta": "+$33", "impact": "Anchors the itinerary.",
                    "rebooked_from": "Was Delta 439 · departed 8:05 AM PT · $214"},
         "updated_at": "2026-07-16T20:00:00+00:00"},
        {"item_id": "i2", "trip_id": "trip-1", "type": "hotel", "status": "booked",
         "location": "Downtown LA", "price": 240.0, "currency": "USD"},
        {"item_id": "i3", "trip_id": "trip-1", "type": "ground", "status": "planned",
         "location": "LAX pickup"},
        {"item_id": "i4", "trip_id": "trip-1", "type": "dining", "status": "broken",
         "location": "First-evening table"},
        {"item_id": "i5", "trip_id": "trip-1", "type": "experience", "status": "repairing",
         "location": "Morning tour"},
        {"item_id": "i6", "trip_id": "trip-1", "type": "flight", "status": "cancelled",
         "location": "old leg"}
      ],
      "summary": {"counts": {"fixed": 1, "booked": 1, "planned": 1, "broken": 1,
                             "repairing": 1, "cancelled": 1}, "all_clear": false},
      "fetched_at": "2026-07-16T20:00:01+00:00",
      "pending_options": {"options": []},
      "consent": {"state": "awaiting_consent",
                  "message": "Waiting for the traveler's go-ahead.",
                  "since": "2026-07-16T19:59:00+00:00",
                  "updated_at": "2026-07-16T19:59:00+00:00"}
    }
    """

    private func decode(_ json: String) throws -> TripStatusResponse {
        try JSONDecoder().decode(TripStatusResponse.self, from: Data(json.utf8))
    }

    func testDeployedShapeFixtureDecodesEverything() throws {
        let status = try decode(fullFixture)

        XCTAssertEqual(status.trip.trip_id, "trip-1")
        XCTAssertEqual(status.items.count, 6)
        XCTAssertEqual(
            Set(status.items.map(\.status)),
            ["planned", "booked", "broken", "repairing", "fixed", "cancelled"]
        )
        XCTAssertEqual(status.summary.counts["repairing"], 1)
        XCTAssertFalse(status.summary.all_clear)

        let consent = try XCTUnwrap(status.consent)
        XCTAssertEqual(consent.state, "awaiting_consent")
        XCTAssertNotNil(consent.message)

        let flight = try XCTUnwrap(status.items.first { $0.item_id == "i1" })
        let details = try XCTUnwrap(flight.details)
        XCTAssertEqual(details.airline_name, "American Airlines")
        XCTAssertEqual(details.flight_number, "118")
        XCTAssertEqual(details.cabin, "Economy")
        XCTAssertEqual(details.duration_minutes, 327)
        XCTAssertEqual(details.stops, 0)
        XCTAssertEqual(details.arrives_next_day, false)
        XCTAssertEqual(
            flight.detail?.rebooked_from,
            "Was Delta 439 · departed 8:05 AM PT · $214"
        )
    }

    func testOmittedBlocksStillDecode() throws {
        let minimal = """
        {
          "trip": {"trip_id": "t2", "title": "Old trip", "status": "booked",
                   "origin": null, "destinations": [],
                   "start_date": null, "end_date": null},
          "items": [
            {"item_id": "i1", "trip_id": "t2", "type": "flight", "status": "booked"}
          ],
          "summary": {"counts": {"booked": 1}, "all_clear": true},
          "fetched_at": "2026-07-16T20:00:01+00:00"
        }
        """
        let status = try decode(minimal)
        XCTAssertNil(status.consent)
        let item = try XCTUnwrap(status.items.first)
        XCTAssertNil(item.details)
        XCTAssertNil(item.detail)
        XCTAssertNil(item.price)
    }

    /// A misshapen additive block (free-form JSON in BigQuery) must degrade
    /// to nil, never fail the whole poll.
    func testMisshapenDetailsBlockDegradesToNil() throws {
        let weird = """
        {
          "trip": {"trip_id": "t3", "title": "Weird", "status": "booked",
                   "origin": null, "destinations": [],
                   "start_date": null, "end_date": null},
          "items": [
            {"item_id": "i1", "trip_id": "t3", "type": "hotel", "status": "booked",
             "details": {"stops": "three", "note": {"nested": true}}}
          ],
          "summary": {"counts": {"booked": 1}, "all_clear": true},
          "fetched_at": "2026-07-16T20:00:01+00:00"
        }
        """
        let status = try decode(weird)
        XCTAssertNil(status.items.first?.details)
    }

    func testPartialRichFieldsProduceNoEmptySeparators() throws {
        // Only cabin present: the facts row must be exactly "Economy" — no
        // dangling "·" from the absent duration/stops.
        let parts = [
            "Economy",
            PacificFormat.duration(minutes: nil),
            PacificFormat.stops(count: nil, layovers: nil),
        ].compactMap { $0 }
        XCTAssertEqual(parts.joined(separator: " · "), "Economy")
        XCTAssertFalse(parts.joined(separator: " · ").contains("nil"))
    }

    func testDemoDisruptResponseDecodesSanitizedFieldsOnly() throws {
        let payload = """
        {"trip_id": "trip-1", "item_id": "i1", "call_id": "call-9",
         "call_status": "queued", "consent": "awaiting_consent"}
        """
        let response = try JSONDecoder().decode(
            DemoDisruptResponse.self, from: Data(payload.utf8)
        )
        XCTAssertEqual(response.trip_id, "trip-1")
        XCTAssertEqual(response.call_status, "queued")
        XCTAssertEqual(response.consent, "awaiting_consent")

        // The decoded model has no field that could carry a callee number,
        // access code, or raw payload — mirror of the backend's scrub.
        let mirror = Mirror(reflecting: response)
        let fieldNames = mirror.children.compactMap(\.label)
        XCTAssertEqual(
            Set(fieldNames),
            ["trip_id", "item_id", "call_id", "call_status", "consent"]
        )
    }

    func testDisruptTimeoutClearsTheVocalBridgeQueueWindow() {
        // place_call blocks 10–16 s before responding; the generic 10 s
        // budget would abandon requests the server goes on to fulfill.
        XCTAssertGreaterThanOrEqual(APIService.disruptTimeout, 30)
    }

    func testErrorBodyPrefersErrorThenDetail() throws {
        let errorBody = try JSONDecoder().decode(
            APIErrorBody.self, from: Data(#"{"error": "VB call failed"}"#.utf8)
        )
        XCTAssertEqual(errorBody.message, "VB call failed")

        let detailBody = try JSONDecoder().decode(
            APIErrorBody.self, from: Data(#"{"detail": "trip x not found"}"#.utf8)
        )
        XCTAssertEqual(detailBody.message, "trip x not found")
    }
}
