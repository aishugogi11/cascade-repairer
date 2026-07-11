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
            accessCode: KeychainHelper.loadAccessCode()
        )))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
