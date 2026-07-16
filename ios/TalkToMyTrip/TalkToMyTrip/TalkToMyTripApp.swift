//
//  TalkToMyTripApp.swift
//  TalkToMyTrip
//
//  Voice-first travel assistant over the Cascade Repairer backend.
//

import SwiftUI

@main
struct TalkToMyTripApp: App {
    @State private var accessManager = AccessManager()

    var body: some Scene {
        WindowGroup {
            // The gate comes first: no stored code, no main screen. A 401
            // on any later call re-locks (see AccessManager), so a rotated
            // code lands the traveler back here instead of erroring out.
            if accessManager.isUnlocked {
                MainTabView()
            } else {
                AccessGateView(accessManager: accessManager)
            }
        }
    }
}
