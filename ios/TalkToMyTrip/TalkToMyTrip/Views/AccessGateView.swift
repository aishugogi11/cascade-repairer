//
//  AccessGateView.swift
//  TalkToMyTrip
//
//  First-launch gate: one field, one button, demo-honest copy. This is a
//  shared demo secret, not a login — no account language anywhere.
//

import SwiftUI

struct AccessGateView: View {
    let accessManager: AccessManager

    @State private var code = ""
    @FocusState private var fieldFocused: Bool

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "airplane.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(.indigo)

            Text("Talk to My Trip")
                .font(.title.bold())

            Text("Enter the access code from your demo invitation")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            TextField("Access code", text: $code)
                .textFieldStyle(.roundedBorder)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($fieldFocused)
                .submitLabel(.go)
                .onSubmit { submit() }
                .padding(.horizontal, 32)

            if let error = accessManager.errorMessage {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            Button {
                submit()
            } label: {
                Group {
                    if accessManager.validating {
                        ProgressView()
                    } else {
                        Text("Continue")
                            .font(.headline)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .disabled(accessManager.validating || code.trimmingCharacters(in: .whitespaces).isEmpty)
            .padding(.horizontal, 32)

            Spacer()
            Spacer()
        }
        .onAppear { fieldFocused = true }
    }

    private func submit() {
        Task { await accessManager.submit(code: code) }
    }
}

#Preview {
    AccessGateView(accessManager: AccessManager())
}
