//
//  ContentView.swift
//  TalkToMyTrip
//
//  The single main screen: voice orb on top, live trip timeline below,
//  demo controls at the bottom. The hidden VoiceWebView rides in the
//  background — in the hierarchy (never detached), invisible.
//

import SwiftUI

struct ContentView: View {
    @State private var voiceManager = VoiceManager()
    @State private var tripManager = TripManager()
    @State private var showAbout = false

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
            .onTapGesture {
                if voiceManager.isConnected {
                    voiceManager.disconnect()
                } else {
                    voiceManager.connect()
                }
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

            demoControls
                .padding(.horizontal)
                .padding(.bottom, 6)
        }
        .background(
            VoiceWebView(voiceManager: voiceManager)
                .frame(width: 1, height: 1)
                .opacity(0)
        )
        .sheet(isPresented: $showAbout) {
            AboutSheetView()
        }
        .task {
            tripManager.start()
        }
        .onChange(of: voiceManager.replyCount) {
            // The agent may have just booked a trip — pick it up next poll.
            tripManager.noteAgentReply()
        }
    }

    /// The reviewer-facing demo: break the flight, then heal it — by voice
    /// ("fix my trip") or with the button fallback.
    private var demoControls: some View {
        HStack(spacing: 10) {
            Button {
                Task { await tripManager.simulateFlightCancellation() }
            } label: {
                Label("Simulate flight cancellation", systemImage: "exclamationmark.triangle")
                    .font(.footnote.bold())
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .tint(.red)
            .disabled(!tripManager.hasBreakableFlight || tripManager.demoActionInFlight)

            Button {
                Task { await tripManager.repairNow() }
            } label: {
                Label("Repair now", systemImage: "wrench.and.screwdriver")
                    .font(.footnote.bold())
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .tint(.green)
            .disabled(tripManager.trip == nil || tripManager.demoActionInFlight)
        }
    }
}

#Preview {
    ContentView()
}
