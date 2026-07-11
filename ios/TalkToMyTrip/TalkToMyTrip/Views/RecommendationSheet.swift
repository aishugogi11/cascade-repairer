//
//  RecommendationSheet.swift
//  TalkToMyTrip
//
//  Card-tap bottom sheet: why the AI chose this piece of the trip, what it
//  cost against the alternatives, and what it means downstream — from the
//  item's `detail` payload, with sensible static copy per item type when
//  the backend didn't send one (the designated cut line).
//

import SwiftUI

struct RecommendationSheet: View {
    let item: ItineraryItem

    private var typeLabel: String {
        switch item.type {
        case "ground": return "Ride"
        case "dining": return "Dining"
        case "experience": return "Experience"
        default: return item.type.capitalized
        }
    }

    private var fallbackWhy: String {
        switch item.type {
        case "flight": return "Chosen for the best balance of schedule and price on your dates."
        case "hotel": return "Placed to match your flight days, close to where the trip happens."
        case "ground": return "Timed to meet your arrival, no waiting around."
        case "dining": return "A first-evening table that fits the schedule."
        case "experience": return "Something worth the free morning on your itinerary."
        default: return "Chosen to fit the rest of your trip."
        }
    }

    private var fallbackImpact: String {
        switch item.type {
        case "flight": return "The rest of the itinerary anchors to this flight's dates and arrival time."
        case "hotel": return "Check-in and check-out line up with the flight days."
        case "ground": return "Pickup is timed to the flight's arrival."
        case "dining": return "The reservation fits the first evening's schedule."
        case "experience": return "Scheduled around the trip's free morning."
        default: return "The rest of the trip stays as planned."
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .foregroundStyle(.indigo)
                Text("AI Recommended")
                    .font(.headline)
                Spacer()
                Text(typeLabel)
                    .font(.caption.bold())
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(.indigo.opacity(0.12), in: Capsule())
                    .foregroundStyle(.indigo)
            }

            if let location = item.location {
                Text(location)
                    .font(.title3.bold())
            }

            row(
                icon: "checkmark.seal",
                title: "Why this one",
                text: item.detail?.why_chosen ?? fallbackWhy
            )
            row(
                icon: "dollarsign.circle",
                title: "Price impact",
                text: item.detail?.price_delta ?? "$0"
            )
            row(
                icon: "arrow.triangle.branch",
                title: "Downstream",
                text: item.detail?.impact ?? fallbackImpact
            )

            Spacer(minLength: 0)
        }
        .padding(24)
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }

    private func row(icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(.secondary)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
                Text(text)
                    .font(.subheadline)
            }
        }
    }
}

#Preview {
    Text("host")
        .sheet(isPresented: .constant(true)) {
            RecommendationSheet(
                item: ItineraryItem(
                    item_id: "1", trip_id: "t", type: "flight", status: "fixed",
                    location: "MSP-SFO", start_ts: nil, end_ts: nil,
                    price: 385, currency: "USD",
                    detail: ItemDetail(
                        why_chosen: "Picked by voice from three options — nonstop, landing at 10:05.",
                        price_delta: "+$33",
                        impact: "The rest of the itinerary anchors to this flight's dates and arrival time."
                    )
                )
            )
        }
}
