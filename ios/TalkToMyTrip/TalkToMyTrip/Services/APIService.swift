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
struct ItemDetail: Codable, Equatable {
    let why_chosen: String?
    let price_delta: String?
    let impact: String?
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

    var id: String { item_id }
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
}

// MARK: - Service

actor APIService {
    static let shared = APIService()

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

    /// Hidden Act 2/3 trigger — the demo orchestrator's disrupt beat.
    /// Places a REAL outbound phone call (10/day Vocal Bridge quota).
    func demoDisrupt(tripID: String) async throws {
        try await post("/v1/demo/disrupt", body: ["trip_id": tripID])
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
