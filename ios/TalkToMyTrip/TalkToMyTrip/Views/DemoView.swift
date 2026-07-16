//
//  DemoView.swift
//  TalkToMyTrip
//
//  The Demo tab: the focused book → cancel → consent call → live repair →
//  summary-call story on one calm native screen. Everything visible is
//  derived from DemoFlowManager's lifecycle state — the view never guesses
//  the flow, and the only repair authorization channel is the traveler's
//  spoken answer on Call 1 (no native approve control exists).
//

import SwiftUI

struct DemoView: View {
    let voiceManager: VoiceManager
    let demoManager: DemoFlowManager

    @State private var showVoiceConsent = false
    /// App-wide voice-data consent — the same flag the Home tab gates on.
    @AppStorage(voiceConsentKey) private var voiceConsentGranted = false

    private var state: DemoLifecycleState { demoManager.lifecycleState }

    private var flightItem: ItineraryItem? {
        demoManager.items.first { $0.type == "flight" }
    }

    private var legItems: [ItineraryItem] {
        demoManager.items.filter { $0.type != "flight" }
    }

    private var disruptAmbiguous: Bool {
        if case .ambiguous = demoManager.disruptPhase { return true }
        return false
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 10) {
                banner
                orb
                voiceError
                DemoTranscriptView(lines: voiceManager.transcript)
                    .padding(.horizontal)
                cards
            }
            .navigationTitle("Talk to My Trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .primaryAction) { newTripButton }
            }
            .safeAreaInset(edge: .bottom) {
                cancelAction
            }
        }
        .sheet(isPresented: $showVoiceConsent) {
            VoiceConsentSheet {
                voiceConsentGranted = true
                voiceManager.connect()
            }
        }
        // Restrained iOS 17 haptics for the story beats — the system
        // suppresses these automatically with the relevant settings.
        .sensoryFeedback(.success, trigger: demoManager.activeTripID) { old, new in
            old == nil && new != nil
        }
        .sensoryFeedback(.warning, trigger: state) { (_, new: DemoLifecycleState) in
            new == .awaitingConsent
        }
        .sensoryFeedback(.impact, trigger: demoManager.changedItemIDs) { (_, new: Set<String>) in
            !new.isEmpty && state == .repairing
        }
        .sensoryFeedback(.success, trigger: state) { (old, new: DemoLifecycleState) in
            old != .recovered && new == .recovered
        }
    }

    private var banner: some View {
        DemoLifecycleBanner(
            state: state,
            consentMessage: demoManager.consent?.message,
            disruptAmbiguous: disruptAmbiguous,
            repairStartedAt: demoManager.repairStartedAt,
            repairElapsed: demoManager.repairElapsed
        )
        .padding(.horizontal)
    }

    private var orb: some View {
        VoiceOrbView(
            orbState: voiceManager.orbState,
            isRepairing: state == .repairing,
            micDenied: voiceManager.micDenied
        )
        .onTapGesture { orbTapped() }
        .accessibilityLabel(voiceManager.isConnected ? "End conversation" : "Start conversation")
        .accessibilityHint(
            state.allowsVoiceConnect
                ? "Talk to your trip by voice."
                : "Voice is paused while your phone call is handled."
        )
    }

    @ViewBuilder
    private var voiceError: some View {
        if let error = voiceManager.lastError {
            Text(error)
                .font(.caption)
                .foregroundStyle(.red)
                .lineLimit(2)
                .padding(.horizontal)
        }
    }

    private var cards: some View {
        ScrollView {
            VStack(spacing: 8) {
                if let flightItem {
                    DemoFlightCardView(
                        item: flightItem,
                        justChanged: demoManager.changedItemIDs.contains(flightItem.item_id)
                    )
                    .transition(.scale(scale: 0.9).combined(with: .opacity))
                }

                ForEach(legItems) { item in
                    DemoLegCardView(
                        item: item,
                        justChanged: demoManager.changedItemIDs.contains(item.item_id)
                    )
                    .transition(.scale(scale: 0.9).combined(with: .opacity))
                }

                if demoManager.trip == nil && state == .booking {
                    ContentUnavailableView(
                        "Ready when you are",
                        systemImage: "airplane.circle",
                        description: Text("Tap the orb and say where you want to go — your new trip builds right here.")
                    )
                    .padding(.top, 8)
                }
            }
            .padding(.horizontal)
            .animation(.spring(duration: 0.5), value: demoManager.items)
        }
    }

    private var newTripButton: some View {
        Button("New trip", systemImage: "plus.circle") {
            demoManager.newTrip()
        }
        .disabled(!state.allowsNewTrip)
        .accessibilityHint("Ends the current conversation and starts the next booking from a clean slate.")
    }

    /// The safe-area action: a visible destructive Cancel flight, armed
    /// only on a complete ready trip (or a stand-down retry).
    private var cancelAction: some View {
        VStack(spacing: 6) {
            if let error = demoManager.disruptError {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal)
            }

            Button(role: .destructive) {
                Task { await demoManager.cancelFlight() }
            } label: {
                Label("Cancel flight", systemImage: "xmark.circle.fill")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
            }
            .buttonStyle(.borderedProminent)
            .tint(.red)
            .disabled(!state.allowsCancel)
            .padding(.horizontal)
            .accessibilityHint(
                state.allowsCancel
                    ? "Cancels your booked flight. Cascade will phone you to ask before repairing anything."
                    : "Available once the whole trip is booked."
            )
        }
        .padding(.top, 6)
        .padding(.bottom, 4)
        .background(.bar)
    }

    private func orbTapped() {
        if voiceManager.isConnected {
            voiceManager.disconnect()
            return
        }
        // No in-app voice while the phone-call flow owns the audio story.
        guard state.allowsVoiceConnect else { return }
        if voiceConsentGranted {
            voiceManager.connect()
        } else {
            showVoiceConsent = true
        }
    }
}

#Preview {
    DemoView(voiceManager: VoiceManager(), demoManager: DemoFlowManager())
}
