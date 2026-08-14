//
//  MainTabView.swift
//  TalkToMyTrip
//
//  The two-tab shell behind the access gate: Demo (default) is the focused
//  book → break → consent → repair story; Home is the original screen kept
//  for reference. Exactly one VoiceManager and one hidden VoiceWebView live
//  here — both tabs share the bridge, so the app can never hold two Vocal
//  Bridge clients or two microphone sessions.
//

import SwiftUI

enum AppTab: Hashable {
    case demo
    case home
}

struct MainTabView: View {
    @State private var voiceManager = VoiceManager()
    @State private var homeTripManager = TripManager()
    @State private var demoManager = DemoFlowManager()
    @State private var selectedTab: AppTab = .demo
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView(selection: $selectedTab) {
            DemoView(voiceManager: voiceManager, demoManager: demoManager)
                .tabItem { Label("Trip", systemImage: "sparkles") }
                .tag(AppTab.demo)

            ReferenceHomeView(
                voiceManager: voiceManager,
                tripManager: homeTripManager
            )
            .tabItem { Label("Home", systemImage: "house") }
            .tag(AppTab.home)
        }
        .background(
            // The one hidden webview — in the hierarchy (detached webviews
            // get throttled), invisible, shared by both tabs.
            VoiceWebView(voiceManager: voiceManager, tripId: nil)
                .frame(width: 1, height: 1)
                .opacity(0)
        )
        .task {
            demoManager.onTripPinChanged = { [weak voiceManager] id in
                voiceManager?.setTrip(id)
            }
            demoManager.onVoiceDisconnectNeeded = { [weak voiceManager] in
                voiceManager?.disconnect()
            }
            demoManager.onNewTripReset = { [weak voiceManager] in
                voiceManager?.disconnect()
                voiceManager?.clearTranscript()
            }
            demoManager.start()
        }
        .onDisappear {
            // The access gate re-locked (401) and the shell is gone — stop
            // both pollers so nothing keeps hitting a 401ing backend.
            demoManager.stop()
            homeTripManager.stop()
            voiceManager.disconnect()
        }
        .onChange(of: selectedTab) { _, newTab in
            // End any live session BEFORE repointing the trip pin — one
            // bridge, one session, never carried across a tab switch.
            voiceManager.disconnect()
            switch newTab {
            case .demo:
                homeTripManager.stop()
                voiceManager.setTrip(demoManager.activeTripID)
                demoManager.resumePolling()
            case .home:
                demoManager.pausePolling()
                voiceManager.setTrip(homeTripManager.tripID)
                homeTripManager.start()
            }
        }
        .onChange(of: scenePhase) { _, newPhase in
            // Returning active after Call 1/2: one immediate poll before
            // the 1.5-second cadence resumes. Voice is never reconnected
            // automatically after an interruption.
            if newPhase == .active, selectedTab == .demo {
                demoManager.pollNow()
            }
        }
        .onChange(of: voiceManager.replyCount) {
            // The agent may have just booked a trip — only the active tab's
            // manager should chase the latest-trip id.
            switch selectedTab {
            case .demo: demoManager.noteAgentReply()
            case .home: homeTripManager.noteAgentReply()
            }
        }
        .onChange(of: demoManager.activeTripID) { _, newValue in
            if selectedTab == .demo { voiceManager.setTrip(newValue) }
        }
        .onChange(of: homeTripManager.tripID) { _, newValue in
            // Home's cold-start resolution or long-press selector — forward
            // only while Home is the active tab so it can never clobber the
            // demo session's pin.
            if selectedTab == .home { voiceManager.setTrip(newValue) }
        }
    }
}

#Preview {
    MainTabView()
}
