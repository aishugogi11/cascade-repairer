//
//  DemoLifecycleBanner.swift
//  TalkToMyTrip
//
//  One compact banner with plain-language copy for every lifecycle state,
//  plus the recovery timer — absent before consent, live during repair,
//  frozen on completion. Short and honest: "Waiting for your go-ahead"
//  before consent (never "repairing"), "Watch for your summary call" after
//  all-clear (never a claim the call was answered).
//

import SwiftUI

struct DemoLifecycleBanner: View {
    let state: DemoLifecycleState
    /// The backend's consent message (stand-down copy comes from here).
    let consentMessage: String?
    let disruptAmbiguous: Bool
    let repairStartedAt: Date?
    let repairElapsed: TimeInterval?

    private var copy: (icon: String, text: String, color: Color) {
        switch state {
        case .booking:
            return ("mic.circle", "Tap the orb and say where you want to go.", .indigo)
        case .building:
            return ("hammer", "Building your trip…", .indigo)
        case .ready:
            return ("checkmark.circle", "Trip confirmed — every reservation is booked.", .blue)
        case .dialing:
            let text = disruptAmbiguous
                ? "Checking whether your call went through…"
                : "Calling you to confirm…"
            return ("phone.arrow.up.right", text, .indigo)
        case .awaitingConsent:
            return ("phone.badge.waveform", "Waiting for your go-ahead on the call.", .red)
        case .standingDown:
            return ("hand.raised", consentMessage ?? "No go-ahead received — nothing was changed.", .orange)
        case .repairing:
            return ("arrow.triangle.2.circlepath", "Repairing your trip…", .orange)
        case .recovered:
            return ("checkmark.seal.fill", "All clear — watch for your summary call.", .green)
        case .reconnecting:
            return ("wifi.slash", "Reconnecting…", .secondary)
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: copy.icon)
                .font(.headline)
                .foregroundStyle(copy.color)
            Text(copy.text)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 6)
            timer
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(copy.color.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Trip status")
        .accessibilityValue(copy.text)
    }

    /// No clock before consent (broken/awaiting show nothing); a live
    /// count-up during repair; the frozen reading once settled.
    @ViewBuilder
    private var timer: some View {
        if state == .repairing, let started = repairStartedAt {
            TimelineView(.periodic(from: started, by: 1)) { context in
                let elapsed = max(0, Int(context.date.timeIntervalSince(started)))
                Label("\(elapsed)s", systemImage: "timer")
                    .font(.subheadline.bold().monospacedDigit())
                    .foregroundStyle(elapsed <= 60 ? Color.orange : .red)
            }
            .accessibilityLabel("Recovery timer")
        } else if state == .recovered, let elapsed = repairElapsed {
            Label("\(Int(elapsed))s", systemImage: "checkmark.seal")
                .font(.subheadline.bold().monospacedDigit())
                .foregroundStyle(.green)
                .accessibilityLabel("Recovered in \(Int(elapsed)) seconds")
        }
    }
}

#Preview {
    VStack(spacing: 8) {
        DemoLifecycleBanner(state: .booking, consentMessage: nil, disruptAmbiguous: false, repairStartedAt: nil, repairElapsed: nil)
        DemoLifecycleBanner(state: .awaitingConsent, consentMessage: nil, disruptAmbiguous: false, repairStartedAt: nil, repairElapsed: nil)
        DemoLifecycleBanner(state: .repairing, consentMessage: nil, disruptAmbiguous: false, repairStartedAt: Date(), repairElapsed: nil)
        DemoLifecycleBanner(state: .recovered, consentMessage: nil, disruptAmbiguous: false, repairStartedAt: nil, repairElapsed: 42)
    }
    .padding()
}
