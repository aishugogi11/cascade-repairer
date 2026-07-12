//
//  AccessManager.swift
//  TalkToMyTrip
//
//  The access-code gate's state: unlocked when a code is in the Keychain,
//  validated once against POST /v1/auth/validate on first launch. A 401 on
//  any later API call (APIService posts .accessCodeRejected) clears the
//  stored code and returns the app to the gate — that's how a server-side
//  code rotation lands.
//

import Foundation
import Observation

extension Notification.Name {
    /// Posted by APIService when the backend answers 401 — the stored
    /// access code is no longer valid.
    static let accessCodeRejected = Notification.Name("accessCodeRejected")
}

@Observable @MainActor
final class AccessManager {
    var isUnlocked: Bool
    var validating = false
    var errorMessage: String?

    init() {
        // iOS keeps Keychain items across app deletion, so a reinstall would
        // silently skip the gate with a code from a previous install.
        // UserDefaults IS wiped on uninstall — a missing first-launch marker
        // means fresh install: purge any stale code and gate normally.
        if !UserDefaults.standard.bool(forKey: "hasLaunchedBefore") {
            KeychainHelper.deleteAccessCode()
            UserDefaults.standard.set(true, forKey: "hasLaunchedBefore")
        }
        isUnlocked = KeychainHelper.loadAccessCode() != nil
        NotificationCenter.default.addObserver(
            forName: .accessCodeRejected, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                KeychainHelper.deleteAccessCode()
                self?.isUnlocked = false
            }
        }
    }

    /// Validate the typed code against the backend; store it only on a 200.
    func submit(code: String) async {
        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "Enter the access code to continue."
            return
        }
        validating = true
        errorMessage = nil
        defer { validating = false }
        do {
            let valid = try await APIService.shared.validateAccessCode(trimmed)
            if valid {
                KeychainHelper.saveAccessCode(trimmed)
                isUnlocked = true
            } else {
                errorMessage = "That code didn't match — double-check your invitation."
            }
        } catch {
            errorMessage = "Couldn't reach the demo backend — try again in a moment."
        }
    }
}
