//
//  DemoTranscriptView.swift
//  TalkToMyTrip
//
//  The last few traveler/Cascade turns, auto-scrolled to the newest. Lines
//  come only from the bridge's `transcript` events (VoiceManager caps
//  retention); `reply` never adds a line, so agent text can't appear twice.
//

import SwiftUI

struct DemoTranscriptView: View {
    let lines: [TranscriptLine]

    /// Displayed turns — the retained tail is already small, show the
    /// freshest few.
    private var visible: [TranscriptLine] {
        Array(lines.suffix(5))
    }

    var body: some View {
        if visible.isEmpty {
            EmptyView()
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 5) {
                        ForEach(visible) { line in
                            HStack(alignment: .top, spacing: 6) {
                                Text(speaker(for: line.role))
                                    .font(.caption.bold())
                                    .foregroundStyle(line.role == "user" ? Color.indigo : .secondary)
                                Text(line.text)
                                    .font(.caption)
                                    .foregroundStyle(.primary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .id(line.id)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(.horizontal, 4)
                }
                .frame(maxHeight: 88)
                .onChange(of: visible.last?.id) { _, newValue in
                    if let newValue {
                        proxy.scrollTo(newValue, anchor: .bottom)
                    }
                }
            }
            .accessibilityLabel("Conversation transcript")
        }
    }

    private func speaker(for role: String) -> String {
        role == "user" ? "You" : "Cascade"
    }
}

#Preview {
    DemoTranscriptView(lines: [
        TranscriptLine(role: "user", text: "Book me a flight from JFK to LA on the 21st."),
        TranscriptLine(role: "agent", text: "I found three options. Option one on Delta departs at 8:05 AM…"),
    ])
    .padding()
}
