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
                } else {
                    voiceManager.connect()
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
            VoiceWebView(voiceManager: voiceManager)
                .frame(width: 1, height: 1)
                .opacity(0)
        )
        .sheet(isPresented: $showAbout) {
            AboutSheetView()
        }
        .sheet(isPresented: $showTripSelector) {
            TripSelectorSheet(currentTripID: tripManager.tripID) { trip in
                tripManager.selectTrip(trip.trip_id)
            }
        }
        .task {
            tripManager.start()
        }
        .onChange(of: voiceManager.replyCount) {
            // The agent may have just booked a trip — pick it up next poll.
            tripManager.noteAgentReply()
        }
    }
}

#Preview {
    ContentView()
}
