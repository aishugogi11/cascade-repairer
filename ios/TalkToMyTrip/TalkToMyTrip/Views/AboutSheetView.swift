//
//  AboutSheetView.swift
//  TalkToMyTrip
//
//  One paragraph on the app plus the privacy and support pages (served by
//  the backend — the same URLs App Store Connect lists).
//

import SwiftUI

struct AboutSheetView: View {
    /// Called when the user withdraws voice consent, so the host can end any
    /// live voice session immediately.
    var onWithdrawVoiceConsent: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var confirmReset = false
    @AppStorage(voiceConsentKey) private var voiceConsentGranted = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(
                        """
                        Talk to My Trip is your voice travel assistant. \
                        Tap the orb, say where you want to go, and it books \
                        the whole trip — flight, hotel, ride, dinner, and \
                        an activity — then watches over it. If something \
                        breaks, just say so and watch the timeline heal \
                        itself while you keep talking.
                        """
                    )
                    .font(.callout)
                }

                Section {
                    Link(destination: URL(string: "\(APIConfig.baseURL)/v1/legal/privacy")!) {
                        Label("Privacy Policy", systemImage: "hand.raised")
                    }
                    Link(destination: URL(string: "\(APIConfig.baseURL)/v1/legal/support")!) {
                        Label("Support", systemImage: "questionmark.circle")
                    }
                }

                if voiceConsentGranted {
                    Section {
                        // Consent withdrawal (guidelines 5.1.1/5.1.2): ends
                        // any live session and re-asks before the next one.
                        Button(role: .destructive) {
                            voiceConsentGranted = false
                            onWithdrawVoiceConsent()
                        } label: {
                            Label("Withdraw voice consent", systemImage: "mic.slash")
                        }
                    } footer: {
                        Text("Ends the current conversation and stops all voice processing until you consent again. To delete stored data, use the contact on the privacy page.")
                    }
                }

                Section {
                    // The per-device "sign out": forget the stored code and
                    // return to the gate. The notification drives the same
                    // re-lock path a server-side code rotation uses.
                    Button(role: .destructive) {
                        confirmReset = true
                    } label: {
                        Label("Reset access code", systemImage: "key.slash")
                    }
                } footer: {
                    Text("Forgets the access code on this device and returns to the welcome screen.")
                }
            }
            .confirmationDialog(
                "Reset access code?",
                isPresented: $confirmReset,
                titleVisibility: .visible
            ) {
                Button("Reset", role: .destructive) {
                    KeychainHelper.deleteAccessCode()
                    NotificationCenter.default.post(name: .accessCodeRejected, object: nil)
                }
            } message: {
                Text("You'll need to enter the code from your invitation again.")
            }
            .navigationTitle("About")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    AboutSheetView()
}
