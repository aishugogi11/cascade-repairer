//
//  APIService.swift
//  TalkToMyTrip
//
//  Thin async client over the deployed backend — the ios_assessor actor
//  pattern. Field names mirror the FastAPI JSON payloads 1:1 (snake_case
//  on purpose); timestamps stay strings, the UI only displays them.
//

import Foundation

// MARK: - Models (shapes from /v1/itinerary/status, /trips, /latest_trip_id)

struct Trip: Codable, Equatable {
    let trip_id: String
    let title: String
    let status: String
    let origin: String?
    let destinations: [String]
    let start_date: String?
    let end_date: String?
}

/// Why an item is what it is — additive on /status since Phase 17; absent
/// for items without a booking (the sheet falls back to static text).
/// `rebooked_from` (Phase 32) is the preformatted "Was Delta 439 · departed
/// 8:05 AM PT · $214" line for the repaired flight's strike-through.
struct ItemDetail: Codable, Equatable {
    let why_chosen: String?
    let price_delta: String?
    let impact: String?
    let rebooked_from: String?
}

/// The flight item's rich `details` stamp (Phase 33) — every field optional
/// so pre-33 rows and non-flight details dicts still decode.
struct FlightDetails: Codable, Equatable {
    let airline: String?
    let flight_number: String?
    let airline_name: String?
    let cabin: String?
    let duration_minutes: Int?
    let layover_airports: [String]?
    let arrives_next_day: Bool?
    let stops: Int?
}

struct ItineraryItem: Codable, Identifiable, Equatable {
    let item_id: String
    let trip_id: String
    let type: String
    let status: String
    let location: String?
    let start_ts: String?
    let end_ts: String?
    let price: Double?
    let currency: String?
    let detail: ItemDetail?
    let details: FlightDetails?

    var id: String { item_id }
}

extension ItineraryItem {
    /// The additive blocks are best-effort on the backend and free-form
    /// JSON in BigQuery — a surprising shape inside them must degrade to
    /// nil, never fail the whole status poll's decode.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        item_id = try c.decode(String.self, forKey: .item_id)
        trip_id = try c.decode(String.self, forKey: .trip_id)
        type = try c.decode(String.self, forKey: .type)
        status = try c.decode(String.self, forKey: .status)
        location = try c.decodeIfPresent(String.self, forKey: .location)
        start_ts = try c.decodeIfPresent(String.self, forKey: .start_ts)
        end_ts = try c.decodeIfPresent(String.self, forKey: .end_ts)
        price = try c.decodeIfPresent(Double.self, forKey: .price)
        currency = try c.decodeIfPresent(String.self, forKey: .currency)
        detail = try? c.decodeIfPresent(ItemDetail.self, forKey: .detail)
        details = try? c.decodeIfPresent(FlightDetails.self, forKey: .details)
    }
}

/// The consent-gated repair flow's wait state (Phase 23) — additive on
/// /status; absent for trips with no consent history.
struct ConsentStatus: Codable, Equatable {
    let state: String
    let message: String?
    let since: String?
    let updated_at: String?
}

/// POST /v1/demo/disrupt's success payload — only the sanitized fields the
/// backend already scrubs; never the callee number or transport secrets.
struct DemoDisruptResponse: Codable, Equatable {
    let trip_id: String?
    let item_id: String?
    let call_id: String?
    let call_status: String?
    let consent: String?
}

/// The backend's error bodies: JSONResponse {"error": …} on 502/503,
/// HTTPException {"detail": …} otherwise. Only these scrubbed message
/// fields ever reach UI state — never a raw response dump.
struct APIErrorBody: Codable {
    let error: String?
    let detail: String?

    var message: String? { error ?? detail }
}

struct StatusSummary: Codable, Equatable {
    let counts: [String: Int]
    let all_clear: Bool
}

struct TripStatusResponse: Codable {
    let trip: Trip
    let items: [ItineraryItem]
    let summary: StatusSummary
    let fetched_at: String
    let consent: ConsentStatus?
}

extension TripStatusResponse {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        trip = try c.decode(Trip.self, forKey: .trip)
        items = try c.decode([ItineraryItem].self, forKey: .items)
        summary = try c.decode(StatusSummary.self, forKey: .summary)
        fetched_at = try c.decode(String.self, forKey: .fetched_at)
        // Best-effort block: a surprising consent shape degrades to nil
        // rather than failing the poll.
        consent = try? c.decodeIfPresent(ConsentStatus.self, forKey: .consent)
    }
}

struct TripListEntry: Codable, Identifiable {
    let trip_id: String
    let title: String
    let status: String
    let start_date: String?
    let end_date: String?

    var id: String { trip_id }
}

enum APIError: Error {
    case badURL
    case httpStatus(Int)
    case notFound
    case unauthorized
    /// An HTTP error whose body carried a scrubbed backend message
    /// (error/detail) — safe to show in friendly UI copy.
    case server(message: String, status: Int)
}

/// The seam DemoFlowManager talks through — APIService in the app, a fake
/// in tests.
protocol DemoBackend: Sendable {
    func status(tripID: String) async throws -> TripStatusResponse
    func latestTripID() async throws -> String?
    @discardableResult
    func demoDisrupt(tripID: String) async throws -> DemoDisruptResponse
}

// MARK: - Service

actor APIService: DemoBackend {
    static let shared = APIService()

    /// demoDisrupt's endpoint-specific budget: place_call blocks 10–16 s
    /// before the backend even responds, so this must sit comfortably above
    /// that window (the generic request timeout is 10 s).
    static let disruptTimeout: TimeInterval = 45

    private let session: URLSession

    init() {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 10
        session = URLSession(configuration: config)
    }

    func status(tripID: String) async throws -> TripStatusResponse {
        try await get("/v1/itinerary/status/\(tripID)")
    }

    /// The most recently created trip — nil when none exist yet (404).
    func latestTripID() async throws -> String? {
        struct LatestTrip: Codable { let trip_id: String }
        do {
            let latest: LatestTrip = try await get("/v1/sabre_tools/latest_trip_id")
            return latest.trip_id
        } catch APIError.notFound {
            return nil
        }
    }

    func recentTrips() async throws -> [TripListEntry] {
        struct TripList: Codable { let trips: [TripListEntry] }
        let list: TripList = try await get("/v1/itinerary/trips")
        return list.trips
    }

    /// The demo orchestrator's disrupt beat: queues Vocal Bridge Call 1,
    /// then breaks the flight — a REAL outbound phone call (10/day quota).
    /// Endpoint-specific timeout: place_call blocks 10–16 s until the call
    /// is queued, so the generic 10 s budget would abandon requests the
    /// server goes on to fulfill. HTTP errors surface only the backend's
    /// scrubbed error/detail message, never a raw body.
    @discardableResult
    func demoDisrupt(tripID: String) async throws -> DemoDisruptResponse {
        var request = URLRequest(url: try url("/v1/demo/disrupt"))
        request.httpMethod = "POST"
        request.timeoutInterval = Self.disruptTimeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["trip_id": tripID])
        attachAccessCode(&request)
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse,
           !(200..<300).contains(http.statusCode), http.statusCode != 401,
           let message = (try? JSONDecoder().decode(APIErrorBody.self, from: data))?.message {
            throw APIError.server(message: message, status: http.statusCode)
        }
        try check(response)
        return try JSONDecoder().decode(DemoDisruptResponse.self, from: data)
    }

    /// The first-launch gate check. True on 200, false on 401 (wrong code);
    /// anything else throws so network trouble reads differently to the user.
    /// Validated with an explicit header (nothing stored yet), and exempt
    /// from the 401 → .accessCodeRejected notification — a wrong guess at
    /// the gate isn't a rotation.
    func validateAccessCode(_ code: String) async throws -> Bool {
        var request = URLRequest(url: try url("/v1/auth/validate"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["code": code])
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { return false }
        if http.statusCode == 401 { return false }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode)
        }
        return true
    }

    // MARK: - Plumbing

    private func url(_ path: String) throws -> URL {
        guard let url = URL(string: "\(APIConfig.baseURL)\(path)") else {
            throw APIError.badURL
        }
        return url
    }

    /// Every request carries the stored access code — the backend gates
    /// /v1/* on it (Phase 17).
    private func attachAccessCode(_ request: inout URLRequest) {
        if let code = KeychainHelper.loadAccessCode() {
            request.setValue(code, forHTTPHeaderField: "X-Access-Code")
        }
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: try url(path))
        attachAccessCode(&request)
        let (data, response) = try await session.data(for: request)
        try check(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func post(_ path: String, body: [String: Any]) async throws {
        var request = URLRequest(url: try url(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        attachAccessCode(&request)
        let (_, response) = try await session.data(for: request)
        try check(response)
    }

    private func check(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        if http.statusCode == 401 {
            // The stored code no longer works (rotated server-side) — tell
            // the gate, which clears the Keychain and re-locks the app.
            NotificationCenter.default.post(name: .accessCodeRejected, object: nil)
            throw APIError.unauthorized
        }
        if http.statusCode == 404 { throw APIError.notFound }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode)
        }
    }
}
