//
//  VoiceOrbView.swift
//  TalkToMyTrip
//
//  The tappable voice orb: idle / connecting / listening / speaking from
//  the voice bridge, with a spinning "Repairing" ring overriding the look
//  while background repairs run.
//

import SwiftUI

struct VoiceOrbView: View {
    let orbState: OrbState
    let isRepairing: Bool
    let micDenied: Bool

    @State private var breathe = false
    @State private var spin = false

    // Stage-readability (Phase 17): saturated, well-separated hues so
    // idle / listening / speaking read from the back of a room; the orange
    // repairing ring overrides all of them.
    private var orbColors: [Color] {
        if micDenied { return [.gray, .gray.opacity(0.6)] }
        switch orbState {
        case .idle: return [.indigo, .purple]
        case .connecting: return [.indigo, .blue]
        case .listening: return [.blue, .cyan]
        case .speaking: return [.green, .mint]
        }
    }

    private var caption: String {
        if micDenied { return "Microphone needed — enable it in Settings to talk" }
        if isRepairing { return "Repairing your trip…" }
        switch orbState {
        case .idle: return "Tap to talk to your trip"
        case .connecting: return "Connecting…"
        case .listening: return "Listening"
        case .speaking: return "Speaking"
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                // Soft halo, breathing while the session is live.
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [orbColors[0].opacity(0.35), .clear],
                            center: .center, startRadius: 10, endRadius: 90
                        )
                    )
                    .frame(width: 180, height: 180)
                    .scaleEffect(breathe ? 1.08 : 0.94)

                Circle()
                    .fill(
                        LinearGradient(
                            colors: orbColors,
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 120, height: 120)
                    .scaleEffect(orbState == .speaking && !breathe ? 0.96 : 1.0)
                    .shadow(color: orbColors[0].opacity(0.5), radius: 24)

                if isRepairing {
                    Circle()
                        .stroke(
                            AngularGradient(
                                colors: [.orange, .yellow, .orange.opacity(0.1), .orange],
                                center: .center
                            ),
                            style: StrokeStyle(lineWidth: 7, lineCap: .round)
                        )
                        .frame(width: 148, height: 148)
                        .rotationEffect(.degrees(spin ? 360 : 0))
                }

                Image(systemName: micDenied ? "mic.slash.fill" : "mic.fill")
                    .font(.system(size: 34))
                    .foregroundStyle(.white.opacity(0.9))
            }
            .frame(height: 190)

            Text(caption)
                .font(.headline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
                breathe = true
            }
            withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) {
                spin = true
            }
        }
        .animation(.easeInOut(duration: 0.4), value: orbState)
        .animation(.easeInOut(duration: 0.4), value: isRepairing)
    }
}

#Preview {
    VStack(spacing: 24) {
        VoiceOrbView(orbState: .listening, isRepairing: false, micDenied: false)
        VoiceOrbView(orbState: .idle, isRepairing: true, micDenied: false)
    }
}
