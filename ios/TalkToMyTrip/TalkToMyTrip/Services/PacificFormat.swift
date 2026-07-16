//
//  PacificFormat.swift
//  TalkToMyTrip
//
//  The one Pacific formatter for itinerary timestamps, plus duration/fare
//  helpers. Standing rule: the backend stores UTC; every surface renders
//  America/Los_Angeles labeled "PT" — never the device's timezone silently.
//  Every helper returns nil for a missing fact so views can omit it (and
//  its separator) cleanly — no "nil", "unknown", or dangling "·".
//

import Foundation

enum PacificFormat {
    static let pacific = TimeZone(identifier: "America/Los_Angeles")!

    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let clock: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = pacific
        f.dateFormat = "h:mm a"
        return f
    }()

    static func date(fromISO iso: String?) -> Date? {
        guard let iso, !iso.isEmpty else { return nil }
        if let date = isoPlain.date(from: iso) ?? isoFractional.date(from: iso) {
            return date
        }
        // The backend's timestamps carry microseconds
        // ("…T15:05:00.123456+00:00"), which ISO8601DateFormatter rejects —
        // it parses at most millisecond precision. Trim the fraction to
        // three digits and retry.
        if let dotIndex = iso.firstIndex(of: ".") {
            let fractionStart = iso.index(after: dotIndex)
            var fractionEnd = fractionStart
            while fractionEnd < iso.endIndex, iso[fractionEnd].isNumber {
                fractionEnd = iso.index(after: fractionEnd)
            }
            let fraction = iso[fractionStart..<fractionEnd].prefix(3)
            let trimmed = iso[..<dotIndex] + "." + fraction + iso[fractionEnd...]
            return isoFractional.date(from: String(trimmed))
        }
        return nil
    }

    /// "8:05 AM PT" — nil when the timestamp is absent or unparseable.
    static func time(fromISO iso: String?) -> String? {
        guard let date = date(fromISO: iso) else { return nil }
        return "\(clock.string(from: date)) PT"
    }

    /// "8:05 AM → 4:32 PM PT" (single trailing PT label; "+1 day" is the
    /// caller's suffix from `arrives_next_day`). Degrades to whichever end
    /// exists.
    static func timeRange(departISO: String?, arriveISO: String?) -> String? {
        let depart = date(fromISO: departISO).map { clock.string(from: $0) }
        let arrive = date(fromISO: arriveISO).map { clock.string(from: $0) }
        switch (depart, arrive) {
        case let (d?, a?): return "\(d) → \(a) PT"
        case let (d?, nil): return "\(d) PT"
        case let (nil, a?): return "\(a) PT"
        default: return nil
        }
    }

    /// "5h 12m" / "45m" — nil for missing or zero (the backend's unknown).
    static func duration(minutes: Int?) -> String? {
        guard let minutes, minutes > 0 else { return nil }
        let h = minutes / 60
        let m = minutes % 60
        if h == 0 { return "\(m)m" }
        if m == 0 { return "\(h)h" }
        return "\(h)h \(m)m"
    }

    /// "$385" for USD (the demo's currency), "385 EUR" otherwise.
    static func fare(price: Double?, currency: String?) -> String? {
        guard let price else { return nil }
        let amount = String(format: "%.0f", price.rounded())
        switch currency {
        case nil, "USD": return "$\(amount)"
        case let other?: return "\(amount) \(other)"
        }
    }

    /// "Nonstop" / "1 stop via DEN" / "2 stops via DEN, ORD" — nil when the
    /// backend didn't say (pre-Phase-33 rows).
    static func stops(count: Int?, layovers: [String]?) -> String? {
        guard let count else { return nil }
        if count == 0 { return "Nonstop" }
        let word = count == 1 ? "1 stop" : "\(count) stops"
        if let layovers, !layovers.isEmpty {
            return "\(word) via \(layovers.joined(separator: ", "))"
        }
        return word
    }
}
