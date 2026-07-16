//
//  DemoFlightCardView.swift
//  TalkToMyTrip
//
//  The prominent current-flight card: carrier + flight number headline,
//  PT departure/arrival, fare, and the cabin · duration · stops facts row —
//  each part hidden when its field is absent, so an old trip renders a
//  useful card with no placeholders or dangling separators. After a repair,
//  the prior flight shows as the subdued struck-through "Was …" line from
//  detail.rebooked_from.
//

import SwiftUI

struct DemoFlightCardView: View {
    let item: ItineraryItem
    let justChanged: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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

    /// "Delta 439" from the rich details; falls back to the bare code or
    /// just "Flight" for pre-Phase-33 rows.
    private var headline: String {
        let d = item.details
        let carrier = nonEmpty(d?.airline_name) ?? nonEmpty(d?.airline)
        let number = nonEmpty(d?.flight_number)
        switch (carrier, number) {
        case let (c?, n?): return "\(c) \(n)"
        case let (c?, nil): return c
        default: return "Flight"
        }
    }

    private var timesLine: String? {
        guard var times = PacificFormat.timeRange(
            departISO: item.start_ts, arriveISO: item.end_ts
        ) else { return nil }
        if item.details?.arrives_next_day == true {
            times += " (+1 day)"
        }
        return times
    }

    /// cabin · duration · stops — only the facts the backend sent.
    private var factsLine: String? {
        let parts = [
            nonEmpty(item.details?.cabin),
            PacificFormat.duration(minutes: item.details?.duration_minutes),
            PacificFormat.stops(
                count: item.details?.stops,
                layovers: item.details?.layover_airports
            ),
        ].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private func nonEmpty(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return value
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Image(systemName: "airplane")
                    .font(.title3)
                    .foregroundStyle(statusColor)
                Text(headline)
                    .font(.title3.bold())
                    .lineLimit(1)
                Spacer(minLength: 8)
                HStack(spacing: 5) {
                    Image(systemName: statusIcon)
                        .symbolEffect(
                            .pulse,
                            options: .repeating,
                            isActive: item.status == "repairing" && !reduceMotion
                        )
                    Text(item.status.capitalized)
                }
                .font(.footnote.bold())
                .foregroundStyle(statusColor)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(statusColor.opacity(0.16), in: Capsule())
            }

            if let location = nonEmpty(item.location) {
                Text(location)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 10) {
                if let timesLine {
                    Text(timesLine)
                        .font(.subheadline)
                }
                Spacer(minLength: 0)
                if let fare = PacificFormat.fare(price: item.price, currency: item.currency) {
                    Text(fare)
                        .font(.subheadline.bold())
                }
            }

            if let factsLine {
                Text(factsLine)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            if let was = nonEmpty(item.detail?.rebooked_from) {
                Text(was)
                    .font(.footnote)
                    .strikethrough()
                    .foregroundStyle(.tertiary)
                    .accessibilityLabel("Previous flight: \(was)")
            }
        }
        .padding(16)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(justChanged ? statusColor : .clear, lineWidth: 2.5)
        )
        .animation(reduceMotion ? nil : .spring(duration: 0.5), value: item.status)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Flight, \(headline)")
        .accessibilityValue(accessibilitySummary)
    }

    private var accessibilitySummary: String {
        var parts = [item.status.capitalized]
        if let timesLine { parts.append(timesLine) }
        if let fare = PacificFormat.fare(price: item.price, currency: item.currency) {
            parts.append(fare)
        }
        if let factsLine { parts.append(factsLine) }
        return parts.joined(separator: ", ")
    }
}

#Preview {
    VStack(spacing: 12) {
        DemoFlightCardView(
            item: ItineraryItem(
                item_id: "1", trip_id: "t", type: "flight", status: "fixed",
                location: "JFK → LAX",
                start_ts: "2026-07-21T15:05:00+00:00",
                end_ts: "2026-07-21T21:32:00+00:00",
                price: 385, currency: "USD",
                detail: ItemDetail(
                    why_chosen: nil, price_delta: nil, impact: nil,
                    rebooked_from: "Was Delta 439 · departed 8:05 AM PT · $214"
                ),
                details: FlightDetails(
                    airline: "AA", flight_number: "118", airline_name: "American Airlines",
                    cabin: "Economy", duration_minutes: 327,
                    layover_airports: [], arrives_next_day: false, stops: 0
                )
            ),
            justChanged: false
        )
        DemoFlightCardView(
            item: ItineraryItem(
                item_id: "2", trip_id: "t", type: "flight", status: "booked",
                location: "JFK → LAX", start_ts: nil, end_ts: nil,
                price: nil, currency: nil, detail: nil, details: nil
            ),
            justChanged: false
        )
    }
    .padding()
}
