//
//  DemoLifecycleState.swift
//  TalkToMyTrip
//
//  One pure derivation from the latest poll plus local request state into
//  the Demo tab's lifecycle — the requirements' state table, encoded once.
//  Views consume this; they never guess the flow themselves, and the app
//  never starts repairs itself (the only authorization channel is the
//  traveler's spoken answer on Call 1).
//

import Foundation

/// The five leg types a complete demo trip must have before Cancel arms.
let demoRequiredLegTypes: Set<String> = ["flight", "hotel", "ground", "dining", "experience"]

enum DemoLifecycleState: Equatable {
    /// No active demo trip — orb and booking prompt.
    case booking
    /// A new trip exists but the five booked legs haven't all landed.
    case building
    /// Complete five-leg itinerary, every leg initially booked.
    case ready
    /// A local disrupt request is in flight (or accepted but not yet
    /// visible in the poll) — "Calling you to confirm", nothing optimistic.
    case dialing
    /// Flight broken, waiting on the traveler's spoken answer. No timer.
    case awaitingConsent
    /// Consent declined / timed out / errored — honest stand-down; the
    /// visible action may be re-armed for a deliberate retry.
    case standingDown
    /// Repairs running after the spoken yes.
    case repairing
    /// At least one item fixed and nothing broken/repairing — all clear.
    case recovered
    /// The poll failed after a trip was known — last good payload stays.
    case reconnecting

    /// Cancel flight is armed only on a complete ready trip, or to retry
    /// Call 1 after an explicit stand-down — never after `recovered`.
    var allowsCancel: Bool {
        self == .ready || self == .standingDown
    }

    /// New trip is unavailable while dialing, awaiting consent, or repairing.
    var allowsNewTrip: Bool {
        switch self {
        case .dialing, .awaitingConsent, .repairing: return false
        default: return true
        }
    }

    /// In-app voice reconnection is disabled while the phone-call flow owns
    /// the audio story (approval is phone-only).
    var allowsVoiceConnect: Bool {
        switch self {
        case .dialing, .awaitingConsent, .repairing: return false
        default: return true
        }
    }
}

/// Everything the derivation needs, free of manager or transport state.
struct DemoLifecycleInput {
    var hasActiveDemoTrip: Bool
    /// A local POST /disrupt is in flight, or returned 200 and the poll
    /// hasn't yet shown the break — the server stays authoritative.
    var disruptRequestActive: Bool
    /// The last poll failed while a trip (and payload) was already known.
    var pollFailed: Bool
    var items: [ItineraryItem]
    /// The status payload's consent block state, when present.
    var consentState: String?
}

func deriveDemoLifecycleState(_ input: DemoLifecycleInput) -> DemoLifecycleState {
    guard input.hasActiveDemoTrip else { return .booking }
    if input.disruptRequestActive { return .dialing }
    if input.pollFailed { return .reconnecting }

    let statuses = input.items.map(\.status)
    let anyBroken = statuses.contains("broken")
    let anyRepairing = statuses.contains("repairing")

    // Stand-down wins over the waiting treatment: the flight is still
    // honestly broken, but the wait is over and retry is permitted.
    if let consent = input.consentState,
       ["declined", "timed_out", "error"].contains(consent) {
        return .standingDown
    }

    // Server truth: any repairing item means repairs are running; a granted
    // consent with items still broken is the same beat, a poll ahead of the
    // first repairing flip.
    if anyRepairing || (input.consentState == "granted" && anyBroken) {
        return .repairing
    }

    // Broken with the wait still open (consent awaiting, or the block not
    // yet visible) — red waiting treatment, no clock.
    if anyBroken { return .awaitingConsent }

    if statuses.contains("fixed") && !anyBroken && !anyRepairing {
        return .recovered
    }

    let presentTypes = Set(input.items.map(\.type))
    let allBooked = !input.items.isEmpty && input.items.allSatisfy { $0.status == "booked" }
    if demoRequiredLegTypes.isSubset(of: presentTypes) && allBooked {
        return .ready
    }

    return .building
}
