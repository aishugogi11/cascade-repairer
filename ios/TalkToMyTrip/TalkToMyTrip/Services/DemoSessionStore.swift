//
//  DemoSessionStore.swift
//  TalkToMyTrip
//
//  The Demo tab's only persistence: the active demo trip id (so a phone
//  call, backgrounding, or relaunch resumes the same run) and the
//  clean-slate baseline (the latest trip id captured before booking, so
//  only a NEWLY booked trip is ever adopted). Nothing else belongs here —
//  no transcript, no access code, no private call data in UserDefaults.
//

import Foundation

final class DemoSessionStore {
    private static let activeKey = "demoActiveTripID"
    private static let baselineKey = "demoBaselineTripID"

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// The trip the current demo run owns. Cleared only by New trip.
    var activeDemoTripID: String? {
        get { defaults.string(forKey: Self.activeKey) }
        set {
            if let newValue { defaults.set(newValue, forKey: Self.activeKey) }
            else { defaults.removeObject(forKey: Self.activeKey) }
        }
    }

    /// The backend's latest trip id at clean-slate time — never displayed,
    /// never pinned; only the "different from this" adoption comparator.
    var baselineTripID: String? {
        get { defaults.string(forKey: Self.baselineKey) }
        set {
            if let newValue { defaults.set(newValue, forKey: Self.baselineKey) }
            else { defaults.removeObject(forKey: Self.baselineKey) }
        }
    }
}
