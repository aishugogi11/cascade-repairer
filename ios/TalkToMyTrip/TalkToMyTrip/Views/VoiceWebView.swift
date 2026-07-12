//
//  VoiceWebView.swift
//  TalkToMyTrip
//
//  The hidden WKWebView that runs the Vocal Bridge WebRTC client through
//  the backend's headless /v1/mobile_voice/ page. It must stay in the view
//  hierarchy (hosted at 1×1pt, opacity 0 by ContentView) — fully detached
//  webviews get throttled and the audio session with them.
//

import SwiftUI
import WebKit

struct VoiceWebView: UIViewRepresentable {
    let voiceManager: VoiceManager
    /// The trip on screen when the webview is created — usually nil at
    /// cold start (the latest-trip resolution races the page load); later
    /// changes reach the page through VoiceManager.setTrip instead.
    var tripId: String?

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        config.userContentController.add(voiceManager, name: "vb")

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.uiDelegate = voiceManager
        voiceManager.attach(webView: webView)
        // HTTPS is required for getUserMedia — the page loads from Cloud Run.
        // The gate ran before this view exists, so the code is in the Keychain.
        webView.load(URLRequest(url: APIConfig.mobileVoiceURL(
            accessCode: KeychainHelper.loadAccessCode(),
            tripId: tripId
        )))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
