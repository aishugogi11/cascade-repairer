//
//  ReferenceHomeView.swift
//  TalkToMyTrip
//
//  The original main screen, retained on the Home tab for reference and
//  regression comparison: voice orb on top, live trip timeline below, the
//  hidden gestures intact (triple-tap disrupts, long-press picks a trip).
//  The voice manager and webview are owned by the shell now — this view
//  only borrows the shared bridge.
//

import SwiftUI

struct ReferenceHomeView: View {
    let voiceManager: VoiceManager
    let tripManager: TripManager

    @State private var showAbout = false
    @State private var showTripSelector = false
    @State private var showVoiceConsent = false
    /// Voice-data consent (guidelines 5.1.1/5.1.2): asked before the mic
    /// ever activates, withdrawable from the About sheet. App-wide — the
    /// same flag gates the Demo tab's orb.
    @AppStorage(voiceConsentKey) private var voiceConsentGranted = false

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Text("Talk to My Trip")
                    .font(.title2.bold())
                Spacer()
                Button {
                    showAbout = true
                } label: {
                    Image(systemName: "info.circle")
                        .font(.title3)
                }
                .accessibilityLabel("About")
            }
            .padding(.horizontal)

            VoiceOrbView(
                orbState: voiceManager.orbState,
                isRepairing: tripManager.repairingCount > 0,
                micDenied: voiceManager.micDenied
            )
            // Order matters: the triple-tap must be declared before the
            // single tap so SwiftUI waits for it to fail first.
            .onTapGesture(count: 3) {
                // Hidden Act 2/3 trigger — real outbound call, no button.
                Task { await tripManager.triggerHiddenDisrupt() }
            }
            .onTapGesture {
                if voiceManager.isConnected {
                    voiceManager.disconnect()
                } else if voiceConsentGranted {
                    voiceManager.connect()
                } else {
                    // Consent first — the mic (and every provider behind it)
                    // stays untouched until the traveler agrees.
                    showVoiceConsent = true
                }
            }
            .onLongPressGesture {
                // Hidden operator surface: repoint the timeline at a trip.
                showTripSelector = true
            }
            .accessibilityLabel(voiceManager.isConnected ? "End conversation" : "Start conversation")

            if let error = voiceManager.lastError {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
                    .padding(.horizontal)
            }

            TripTimelineView(tripManager: tripManager)
        }
        .sheet(isPresented: $showAbout) {
            AboutSheetView(onWithdrawVoiceConsent: {
                voiceManager.disconnect()
            })
        }
        .sheet(isPresented: $showVoiceConsent) {
            VoiceConsentSheet {
                voiceConsentGranted = true
                voiceManager.connect()
            }
        }
        .sheet(isPresented: $showTripSelector) {
            TripSelectorSheet(currentTripID: tripManager.tripID) { trip in
                tripManager.selectTrip(trip.trip_id)
            }
        }
        .task {
            tripManager.start()
        }
        .onDisappear {
            // Leaving the tab (or the gate re-locking) pauses this tab's
            // polling; the shell owns voice teardown on tab changes.
            tripManager.stop()
        }
    }
}

#Preview {
    ReferenceHomeView(voiceManager: VoiceManager(), tripManager: TripManager())
}
