//
//  DemoLegCardView.swift
//  TalkToMyTrip
//
//  One compact downstream reservation (hotel / ride / dining / experience):
//  icon, label, location, and a lifecycle badge that reads by icon + text +
//  color together — never color alone.
//

import SwiftUI

struct DemoLegCardView: View {
    let item: ItineraryItem
    let justChanged: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var typeIcon: String {
        switch item.type {
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
        default: return .gray
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
        HStack(spacing: 10) {
            Image(systemName: typeIcon)
                .font(.subheadline)
                .frame(width: 32, height: 32)
                .background(statusColor.opacity(0.14), in: Circle())
                .foregroundStyle(statusColor)

            VStack(alignment: .leading, spacing: 1) {
                Text(typeLabel)
                    .font(.subheadline.bold())
                    .lineLimit(1)
                if let location = item.location, !location.isEmpty {
                    Text(location)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 6)

            HStack(spacing: 4) {
                Image(systemName: statusIcon)
                    .symbolEffect(
                        .pulse,
                        options: .repeating,
                        isActive: item.status == "repairing" && !reduceMotion
                    )
                Text(item.status.capitalized)
            }
            .font(.caption.bold())
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .foregroundStyle(statusColor)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(statusColor.opacity(0.14), in: Capsule())
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 13))
        .overlay(
            RoundedRectangle(cornerRadius: 13)
                .stroke(justChanged ? statusColor : .clear, lineWidth: 2)
        )
        .animation(reduceMotion ? nil : .spring(duration: 0.5), value: item.status)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(typeLabel)
        .accessibilityValue("\(item.status.capitalized)\(item.location.map { ", \($0)" } ?? "")")
    }
}

#Preview {
    VStack(spacing: 8) {
        DemoLegCardView(
            item: ItineraryItem(
                item_id: "1", trip_id: "t", type: "hotel", status: "repairing",
                location: "Downtown LA", start_ts: nil, end_ts: nil,
                price: 240, currency: "USD", detail: nil, details: nil
            ),
            justChanged: true
        )
        DemoLegCardView(
            item: ItineraryItem(
                item_id: "2", trip_id: "t", type: "dining", status: "booked",
                location: "First-evening table", start_ts: nil, end_ts: nil,
                price: nil, currency: nil, detail: nil, details: nil
            ),
            justChanged: false
        )
    }
    .padding()
}
