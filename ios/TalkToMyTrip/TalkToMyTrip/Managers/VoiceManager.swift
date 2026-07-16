//
//  VoiceManager.swift
//  TalkToMyTrip
//
//  Owns the hidden voice webview: decodes the JSON events the headless
//  /v1/mobile_voice/ page posts through the "vb" message handler into
//  observable state, and drives the page with vbConnect()/vbDisconnect()
//  via evaluateJavaScript. All WebKit callbacks arrive on the main thread.
//

import AVFoundation
import Foundation
import Observation
import WebKit

enum OrbState {
    case idle
    case connecting
    case listening
    case speaking
}

struct TranscriptLine: Identifiable {
    let id = UUID()
    let role: String
    let text: String
}

@Observable
final class VoiceManager: NSObject {
    var connectionState: String = "disconnected"
    var orbState: OrbState = .idle
    var transcript: [TranscriptLine] = []
    var lastError: String?
    /// Bumped on every agent reply — TripManager re-resolves the latest trip
    /// on it so a trip booked by voice mid-session appears without restart.
    var replyCount = 0
    /// Set when the user declines the mic prompt so the UI can explain
    /// itself; the rest of the app (timeline, demo buttons) keeps working.
    var micDenied = false

    private(set) var webView: WKWebView?
    private var speakingResetTask: Task<Void, Never>?
    private var interruptionObserver: NSObjectProtocol?

    override init() {
        super.init()
        // A phone call (Call 1/2 of the demo) interrupts the audio session:
        // end the webview session and leave the orb honestly idle — the
        // user reconnects deliberately, never automatically.
        interruptionObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            guard let info = note.userInfo,
                  let raw = info[AVAudioSessionInterruptionTypeKey] as? UInt,
                  AVAudioSession.InterruptionType(rawValue: raw) == .began else { return }
            Task { @MainActor in self?.disconnect() }
        }
    }

    deinit {
        if let interruptionObserver {
            NotificationCenter.default.removeObserver(interruptionObserver)
        }
    }

    var isConnected: Bool {
        connectionState.lowercased().contains("connected")
            && !connectionState.lowercased().contains("dis")
    }

    func attach(webView: WKWebView) {
        self.webView = webView
    }

    /// Ask for the mic natively first — one system prompt, owned by the
    /// app; the WKUIDelegate grant below keeps the webview from adding a
    /// second one. A denial leaves the rest of the app fully usable.
    func connect() {
        lastError = nil
        switch AVAudioApplication.shared.recordPermission {
        case .granted:
            startSession()
        case .denied:
            micDenied = true
        case .undetermined:
            AVAudioApplication.requestRecordPermission { [weak self] granted in
                Task { @MainActor in
                    guard let self else { return }
                    if granted {
                        self.micDenied = false
                        self.startSession()
                    } else {
                        self.micDenied = true
                    }
                }
            }
        @unknown default:
            startSession()
        }
    }

    private func startSession() {
        orbState = .connecting
        webView?.evaluateJavaScript("window.vbConnect && window.vbConnect()")
    }

    func disconnect() {
        webView?.evaluateJavaScript("window.vbDisconnect && window.vbDisconnect()")
        orbState = .idle
    }

    /// Tell the voice page which trip the app is displaying — the page sends
    /// it with every delegated query so the session pins that trip (the
    /// server ignores it once a trip is pinned). Called on every displayed-
    /// trip change, which closes the race where the webview loads before the
    /// cold-start latest-trip resolution lands.
    /// nil clears the page's pin (the clean-slate booking state —
    /// vbSetTrip('') on the page). The id is sanitized to the characters a
    /// trip id can contain before being interpolated into JavaScript.
    func setTrip(_ tripId: String?) {
        let safe = (tripId ?? "").filter {
            $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_"
        }
        webView?.evaluateJavaScript(
            "window.vbSetTrip && window.vbSetTrip('\(safe)')"
        )
    }

    /// New trip: the demo's transcript starts clean without touching the
    /// connection state machinery.
    func clearTranscript() {
        transcript.removeAll()
    }

    private func updateOrb(forState value: String) {
        let state = value.lowercased()
        if state.contains("disconnect") {
            orbState = .idle
        } else if state.contains("connecting") || state.contains("waiting") {
            orbState = .connecting
        } else if state.contains("connected") {
            // Listening is the connected resting state; replies flip to
            // speaking below and decay back here.
            if orbState != .speaking { orbState = .listening }
        }
    }

    private func flashSpeaking() {
        orbState = .speaking
        speakingResetTask?.cancel()
        speakingResetTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(4))
            guard let self, !Task.isCancelled else { return }
            if self.orbState == .speaking, self.isConnected {
                self.orbState = .listening
            }
        }
    }
}

// MARK: - Webview → native events

extension VoiceManager: WKScriptMessageHandler {
    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == "vb",
              let body = message.body as? [String: Any],
              let type = body["type"] as? String else { return }

        switch type {
        case "state":
            let value = body["value"] as? String ?? ""
            connectionState = value
            updateOrb(forState: value)
        case "transcript":
            transcript.append(TranscriptLine(
                role: body["role"] as? String ?? "unknown",
                text: body["text"] as? String ?? ""
            ))
            // Bounded on purpose: the Demo tab shows only the last few
            // turns, and `reply` never adds lines — agent text can't
            // appear twice or grow without limit.
            if transcript.count > 12 {
                transcript.removeFirst(transcript.count - 12)
            }
        case "reply":
            replyCount += 1
            flashSpeaking()
        case "error":
            lastError = body["message"] as? String ?? "unknown voice error"
            if orbState == .connecting { orbState = .idle }
        default:
            break
        }
    }
}

// MARK: - Native → webview mic grant

extension VoiceManager: WKUIDelegate {
    /// iOS already asked natively (NSMicrophoneUsageDescription); granting
    /// the webview's capture request suppresses the second prompt.
    func webView(
        _ webView: WKWebView,
        requestMediaCapturePermissionFor origin: WKSecurityOrigin,
        initiatedByFrame frame: WKFrameInfo,
        type: WKMediaCaptureType,
        decisionHandler: @escaping (WKPermissionDecision) -> Void
    ) {
        decisionHandler(.grant)
    }
}
