//
//  ContentView.swift
//  TalkToMyTrip
//
//  The single main screen: voice orb on top, live trip timeline below.
//  No visible demo controls — the stage triggers are hidden gestures on
//  the orb (triple-tap disrupts, long-press picks a trip). The hidden
//  VoiceWebView rides in the background — in the hierarchy (never
//  detached), invisible.
//

import SwiftUI

struct ContentView: View {
    @State private var voiceManager = VoiceManager()
    @State private var tripManager = TripManager()
    @State private var showAbout = false
    @State private var showTripSelector = false
    @State private var showVoiceConsent = false
    /// Voice-data consent (guidelines 5.1.1/5.1.2): asked before the mic
    /// ever activates, withdrawable from the About sheet.
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
        .background(
            VoiceWebView(voiceManager: voiceManager, tripId: tripManager.tripID)
                .frame(width: 1, height: 1)
                .opacity(0)
        )
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
            // The access gate re-locked (401 → AccessManager) and this view
            // is gone — without this, the poll task retains TripManager and
            // polls a 401ing backend forever.
            tripManager.stop()
            voiceManager.disconnect()
        }
        .onChange(of: voiceManager.replyCount) {
            // The agent may have just booked a trip — pick it up next poll.
            tripManager.noteAgentReply()
        }
        .onChange(of: tripManager.tripID) { _, newValue in
            // Every displayed-trip change (cold-start resolution landing,
            // long-press selector) reaches the voice page, so the session
            // pins the trip on screen — the URL param alone loses the race
            // with the cold-start latest-trip resolution.
            if let newValue { voiceManager.setTrip(newValue) }
        }
    }
}

#Preview {
    ContentView()
}
