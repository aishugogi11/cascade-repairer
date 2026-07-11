//
//  KeychainHelper.swift
//  TalkToMyTrip
//
//  Minimal Keychain wrapper for the one secret this app holds: the shared
//  demo access code. No dependencies, three operations.
//

import Foundation
import Security

enum KeychainHelper {
    private static let service = "com.zensoftware.talktomytrip"
    private static let account = "demo-access-code"

    private static var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    static func saveAccessCode(_ code: String) {
        deleteAccessCode()
        var query = baseQuery
        query[kSecValueData as String] = Data(code.utf8)
        SecItemAdd(query as CFDictionary, nil)
    }

    static func loadAccessCode() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let code = String(data: data, encoding: .utf8),
              !code.isEmpty else {
            return nil
        }
        return code
    }

    static func deleteAccessCode() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}
