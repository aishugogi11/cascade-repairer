//
//  ItineraryCardView.swift
//  TalkToMyTrip
//
//  One itinerary item: type icon, location, and a status badge that
//  animates through the repair lifecycle booked → broken → repairing →
//  fixed. Pulses when its status just changed.
//

import SwiftUI

struct ItineraryCardView: View {
    let item: ItineraryItem
    let justChanged: Bool

    private var typeIcon: String {
        switch item.type {
        case "flight": return "airplane"
        case "hotel": return "bed.double.fill"
        case "ground": return "car.fill"
        case "dining": return "fork.knife"
        case "experience": return "ticket.fill"
        default: return "mappin"
        }
    }

    private var typeLabel: String {
        switch item.type {
        case "ground": return "Ride"
        case "dining": return "Dining"
        case "experience": return "Experience"
        default: return item.type.capitalized
        }
    }

    private var statusColor: Color {
        switch item.status {
        case "booked": return .blue
        case "broken": return .red
        case "repairing": return .orange
        case "fixed": return .green
        case "cancelled": return .gray
        default: return .gray  // planned
        }
    }

    private var statusIcon: String {
        switch item.status {
        case "booked": return "checkmark.circle"
        case "broken": return "exclamationmark.triangle.fill"
        case "repairing": return "arrow.triangle.2.circlepath"
        case "fixed": return "checkmark.seal.fill"
        case "cancelled": return "xmark.circle"
        default: return "circle.dashed"
        }
    }

    var body: some View {
        // Stage-readability (Phase 17): larger type, icons, and badge, with
        // higher-contrast status colors — legible on a projected phone
        // screen from the back of a room.
        HStack(spacing: 14) {
            Image(systemName: typeIcon)
                .font(.title2)
                .frame(width: 46, height: 46)
                .background(statusColor.opacity(0.18), in: Circle())
                .foregroundStyle(statusColor)

            VStack(alignment: .leading, spacing: 3) {
                Text(typeLabel)
                    .font(.title3.bold())
                    .lineLimit(1)
                if let location = item.location {
                    Text(location)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 8)

            // The badge never wraps or truncates — the location text on the
            // left is what gives way on narrow screens.
            HStack(spacing: 6) {
                Image(systemName: statusIcon)
                    .symbolEffect(
                        .pulse,
                        options: .repeating,
                        isActive: item.status == "repairing"
                    )
                Text(item.status.capitalized)
            }
            .font(.subheadline.bold())
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .foregroundStyle(statusColor)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(statusColor.opacity(0.18), in: Capsule())
        }
        .padding(14)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(justChanged ? statusColor : .clear, lineWidth: 3)
        )
        .scaleEffect(justChanged ? 1.02 : 1.0)
        .animation(.spring(duration: 0.5), value: item.status)
        .animation(.spring(duration: 0.5), value: justChanged)
    }
}

#Preview {
    VStack {
        ItineraryCardView(
            item: ItineraryItem(
                item_id: "1", trip_id: "t", type: "flight", status: "repairing",
                location: "MSP-SFO", start_ts: nil, end_ts: nil,
                price: 385, currency: "USD", detail: nil, details: nil
            ),
            justChanged: true
        )
    }
    .padding()
}
