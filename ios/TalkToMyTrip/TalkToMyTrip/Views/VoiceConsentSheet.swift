//
//  VoiceConsentSheet.swift
//  TalkToMyTrip
//
//  First-use consent before the microphone ever activates (App Review
//  guidelines 5.1.1/5.1.2): names every third party that processes voice
//  data — Vocal Bridge, OpenAI, Google Cloud — and offers a real decline.
//  Consent can be withdrawn later from the About sheet.
//

import SwiftUI

/// UserDefaults key for the voice-data consent flag — read by ContentView
/// before any connect, cleared by the About sheet's withdraw action.
let voiceConsentKey = "voiceConsentGranted"

struct VoiceConsentSheet: View {
    /// Called when the user consents — the caller stores the flag and starts
    /// the voice session.
    let onContinue: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Before you talk")
                .font(.title2.bold())
                .padding(.top, 8)

            Text("Voice conversations are processed by these services:")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            row(
                icon: "waveform",
                title: "Vocal Bridge",
                text: "Hears your voice and speaks the assistant's replies."
            )
            row(
                icon: "brain",
                title: "OpenAI",
                text: "An AI model reads the conversation text to plan and book your trip."
            )
            row(
                icon: "externaldrive",
                title: "Google Cloud",
                text: "Stores transcripts and trip data. Deleted within 90 days."
            )

            Text("You can withdraw consent anytime in About, and the rest of the app works without voice.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Link(destination: URL(string: "\(APIConfig.baseURL)/v1/legal/privacy")!) {
                Text("Privacy Policy")
                    .font(.footnote)
            }

            Spacer(minLength: 0)

            Button {
                dismiss()
                onContinue()
            } label: {
                Text("Continue")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)

            Button {
                dismiss()
            } label: {
                Text("Not now")
                    .font(.subheadline)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .padding(.bottom, 8)
        }
        .padding(24)
        // Full-height: every disclosure line and both buttons visible at
        // once — a consent screen must never open pre-clipped.
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    private func row(icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(.indigo)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.bold())
                Text(text)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    // Disclosure text must never truncate — wrap instead.
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

#Preview {
    Text("host")
        .sheet(isPresented: .constant(true)) {
            VoiceConsentSheet {}
        }
}
