# Requirements — Search-hardening close-out (Phase 30)

Remediation of the four gaps from the Phase 28 validation report
(`specs/2026-07-14-search-hardening/validation-report.md`), kept deliberately
small so Phase 29 (real repair data) starts from validated ground. Two are
test-only, one is a real behavior fix, one is a dev-tooling fix.

## Scope

### In scope

| # | Item | Type | Source in report |
|---|------|------|------------------|
| 1 | Six-case metro-alias test — `NYC→JFK`, `WAS→IAD`, `CHI→ORD` in **both** request positions | Test only | Criterion 6 FAIL; "Missing tests" |
| 2 | POST-path 401 token-refresh test — `_post` retries once with a fresh bearer, raises on a second 401 | Test only | Criterion 5 note; "Missing tests" |
| 3 | Clear stale flight options on **every non-optioned return** of `search_flights_impl` | Behavior fix | "Risks not covered": stale choice after empty repeat search |
| 4 | Pin `git_pull_dev.sh` default base branch to `vb/dev` | Tooling fix | "Risks not covered": unrelated branch-automation change |

### Data / behavior table — item 3 (clear-on returns)

`search_flights_impl` (`backend/api/concierge.py:422`) has four returns that
hand back a speakable string **without** producing options. Today only the two
*optioned* returns touch state (writes) and only `book_flight_impl` clears it,
so any of these four leaves the previous search's `_SESSION_FLIGHT_OPTIONS` and
`_LATEST_SEARCH` intact — a traveler told "no flights" can still book a stale
choice by number.

| Return branch | Line (approx) | Clears today? | Must clear after |
|---------------|---------------|---------------|------------------|
| Missing origin/destination/date | 434 | no | yes |
| Unsupported market | 445 | no | yes |
| Search error (exception) | 455 | no | yes |
| No options found (honest empty) | 457 | no | yes |
| Optioned (1 result) | 472 | writes | n/a — stores fresh options |
| Optioned (2–3 results) | 477 | writes | n/a — stores fresh options |

"Clear" means: `_SESSION_FLIGHT_OPTIONS.pop(session_id, None)` **and** set
`_LATEST_SEARCH = None` **only when** `_LATEST_SEARCH.session_id == session_id`
(the exact ownership guard already used in `book_flight_impl` at
`concierge.py:583`) — never wipe another session's in-flight slot.

### Not included

- Phase 29 (real repair data) — the next phase; nothing here touches
  `repair_tools.py` or the BFM→InstaFlights repair swap.
- Phase 22's `_LATEST_SEARCH` expiry hardening — complementary and unchanged;
  item 3 is about *clearing on non-result*, not *expiring on age*.
- The Phase 24 conditional punch list (dead `POS` field, empty-BFM shapes,
  BM-errors-as-200) — retired with the 2026-07-14 no-entitlement-ask decision.
- Any new dependency, endpoint, page, or schema change.

## Decisions

1. **All four items ship together** (user, interview). They are the report's
   complete remediation set; splitting them risks Phase 29 building on
   un-hardened ground (the Phase 26 precedent — a close-out lands before the
   next phase builds on the same path).
2. **Clear on every non-optioned return, not just the honest-empty path**
   (user, interview). Matches the roadmap wording ("clear both on every
   non-optioned return"). Narrower would leave the error and unsupported-market
   windows open.
3. **`_LATEST_SEARCH` is cleared ownership-guarded**, mirroring
   `book_flight_impl` exactly — no new clearing idiom, so the two code paths
   that touch the module-level slot stay identical in their guard.
4. **The POST-path 401 test drives `_post` directly** through the same
   `MockTransport` factory the GET tests use (`_mock_transport`,
   `_configured_real_client`). The report names `_post`; a direct call avoids
   coupling the test to any one endpoint's response shape while still proving
   the shared `_send_with_refresh` retry through the POST send closure.
5. **Metro-alias test is one parametrized function** over the three aliases ×
   two positions (6 cases), asserting for each that (a) the normalized pair
   reaches market validation and (b) the captured client request carries the
   airport code, not the metro code — the literal six-case reading the report
   applied. The existing single-case `test_metro_codes_alias_to_airports_before_the_market_check`
   and `test_non_alias_codes_pass_through_untouched` stay as-is.
6. **`git_pull_dev.sh` gets `vb/dev` as the first resolution step** — a new
   branch `0.` ahead of the existing `BASE_BRANCH` env / `gh` / `origin/HEAD`
   chain, with the comment block updated. An explicit `BASE_BRANCH=…` override
   still wins (keep it as the highest-precedence escape hatch). Rationale: this
   repo's integration branch is `vb/dev`, but `origin/HEAD` resolves to
   `origin/main` here, and the script merges with `--admin` immediately — the
   wrong default is a live foot-gun.
7. **PR evidence is pre-merge** (user, interview). The Definition of Done
   requires the cert run and reachable walkthroughs to be pasted into the PR
   description as transcript/output snippets **before merge** — not prose
   claims or "see comments." This is the direct process lesson from Phase 28's
   two FAILs (DoD A and B).

## Context

- **Tone:** item 3 touches no user-facing copy — the four non-optioned return
  strings are unchanged; only the state-clearing is added. No new jargon.
- **Stack pointers:** `backend/api/concierge.py` (`search_flights_impl`, the
  `_SESSION_FLIGHT_OPTIONS` / `_LATEST_SEARCH` slots, the `book_flight_impl`
  clearing idiom to mirror); `backend/api/sabre/real_client.py`
  (`_post` / `_send_with_refresh`); `backend/tests/test_sabre_instaflights.py`
  (the `_mock_transport` / `_configured_real_client` helpers and the existing
  GET 401 + single-alias tests to pattern-match); `git_pull_dev.sh` at repo
  root.
- **Existing patterns to follow:** tests use computed dates (`_DAY`,
  `_NEXT_DAY` from `date.today()`), never literals (criterion 8) — the new
  tests must too. The mock-transport tests route the real client's inline
  `httpx.AsyncClient` through `httpx.MockTransport`; no network, no credentials
  (hermetic — CI runs the bare suite in-container).
- **Timezone / dates:** unchanged; no date-handling code is touched.
- **Open question resolved:** the report asked whether criterion 6 needs six
  committed assertions — this spec answers **yes** (decision 5).
