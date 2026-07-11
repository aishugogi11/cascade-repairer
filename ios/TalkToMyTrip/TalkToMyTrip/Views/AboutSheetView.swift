//
//  AboutSheetView.swift
//  TalkToMyTrip
//
//  One paragraph on the app plus the privacy and support pages (served by
//  the backend — the same URLs App Store Connect lists).
//

import SwiftUI

struct AboutSheetView: View {
    @Environment(\.dismiss) private var dismiss

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
