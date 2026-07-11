//
//  TripSelectorSheet.swift
//  TalkToMyTrip
//
//  Hidden operator surface (long-press the orb): recent trips from
//  GET /v1/itinerary/trips; picking one repoints the timeline's polling.
//

import SwiftUI

struct TripSelectorSheet: View {
    let currentTripID: String?
    let onSelect: (TripListEntry) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var trips: [TripListEntry] = []
    @State private var loading = true
    @State private var loadFailed = false

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    ProgressView("Loading trips…")
                } else if loadFailed {
                    ContentUnavailableView(
                        "Couldn't load trips",
                        systemImage: "wifi.slash",
                        description: Text("Check the connection and try again.")
                    )
                } else if trips.isEmpty {
                    ContentUnavailableView(
                        "No trips yet",
                        systemImage: "airplane.circle",
                        description: Text("Book one by voice and it will appear here.")
                    )
                } else {
                    List(trips) { trip in
                        Button {
                            onSelect(trip)
                            dismiss()
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(trip.title)
                                        .font(.headline)
                                        .lineLimit(1)
                                    if let start = trip.start_date, let end = trip.end_date {
                                        Text("\(start) → \(end)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                if trip.trip_id == currentTripID {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(.tint)
                                }
                            }
                        }
                        .foregroundStyle(.primary)
                    }
                }
            }
            .navigationTitle("Recent Trips")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .task {
            do {
                trips = try await APIService.shared.recentTrips()
            } catch {
                loadFailed = true
            }
            loading = false
        }
    }
}

#Preview {
    Text("host")
        .sheet(isPresented: .constant(true)) {
            TripSelectorSheet(currentTripID: nil) { _ in }
        }
}
