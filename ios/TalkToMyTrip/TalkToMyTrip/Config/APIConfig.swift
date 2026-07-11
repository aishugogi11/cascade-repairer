//
//  APIConfig.swift
//  TalkToMyTrip
//
//  API environment selection — the ios_assessor pattern, scaled down.
//  Change `currentEnvironment` to switch between Cloud Run and the local
//  docker compose backend.
//

import Foundation

enum APIEnvironment {
    /// docker compose on the dev machine — simulator testing only. Note the
    /// voice webview needs HTTPS for getUserMedia, so voice is exercised
    /// against Cloud Run even during local API testing.
    case local
    /// The deployed Cloud Run service — App Store builds use this.
    case development

    var baseURL: String {
        switch self {
        case .local:
            return "http://localhost:1019"
        case .development:
            return "https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app"
        }
    }
}

struct APIConfig {
    static let currentEnvironment: APIEnvironment = .development

    static var baseURL: String {
        currentEnvironment.baseURL
    }

    /// The headless Vocal Bridge bridge page the hidden webview loads. The
    /// access code rides as ?code= so the page's token/query fetches can
    /// attach the X-Access-Code header behind the Phase 17 gate.
    static func mobileVoiceURL(accessCode: String?) -> URL {
        var components = URLComponents(string: "\(baseURL)/v1/mobile_voice/")!
        if let accessCode, !accessCode.isEmpty {
            components.queryItems = [URLQueryItem(name: "code", value: accessCode)]
        }
        return components.url!
    }
}
