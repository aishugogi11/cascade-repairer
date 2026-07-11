//
//  TripTimelineView.swift
//  TalkToMyTrip
//
//  The live trip timeline: five cards with spring inserts as items appear
//  in the polls, plus the recovery timer against the 60-second target.
//

import SwiftUI

struct TripTimelineView: View {
    let tripManager: TripManager

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                if let trip = tripManager.trip {
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
                        recoveryTimer
                    }
                    .padding(.horizontal, 2)
                }

                ForEach(tripManager.items) { item in
                    ItineraryCardView(
                        item: item,
                        justChanged: tripManager.changedItemIDs.contains(item.item_id)
                    )
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
                }

                if tripManager.trip == nil {
                    ContentUnavailableView(
                        "No trip yet",
                        systemImage: "airplane.circle",
                        description: Text("Tap the orb and say where you want to go — your trip will appear here.")
                    )
                    .padding(.top, 12)
                }

                if tripManager.pollFailed {
                    Label("Reconnecting…", systemImage: "wifi.slash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }
            }
            .padding(.horizontal)
            .animation(.spring(duration: 0.6), value: tripManager.items)
        }
    }

    @ViewBuilder
    private var recoveryTimer: some View {
        if let started = tripManager.recoveryStartedAt {
            // Live count-up while the trip heals, against the 60s target.
            TimelineView(.periodic(from: started, by: 1)) { context in
                let elapsed = Int(context.date.timeIntervalSince(started))
                Label("\(elapsed)s / 60s", systemImage: "timer")
                    .font(.caption.bold().monospacedDigit())
                    .foregroundStyle(elapsed <= 60 ? .orange : .red)
            }
        } else if let elapsed = tripManager.recoveryElapsed {
            Label("Recovered in \(Int(elapsed))s", systemImage: "checkmark.seal.fill")
                .font(.caption.bold())
                .foregroundStyle(.green)
        }
    }
}
