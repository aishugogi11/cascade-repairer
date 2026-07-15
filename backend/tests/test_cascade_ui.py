"""Cascade dashboard page tests — Phase 22, hermetic (no GCP, no network).

Run against the real main.app so the router registration and the
access-gate allowlisting are both under test — the page shell must stay
reachable without a code while the JSON endpoints it polls stay gated.
The shell-wiring assertions mirror test_booking_ui.py; the trigger-control
assertions check the markup only — the /v1/demo endpoints place real calls
and need env, and the orchestrator itself is covered by test_demo.py.
"""
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

CODE = "demo-code-1234"


def test_shell_served_without_code_when_gate_armed(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    resp = client.get("/v1/cascade/")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Cascade Dashboard — Cascade Repairer" in resp.text


def test_gated_json_endpoints_still_401_without_code(monkeypatch):
    """The shell is inert without the gated APIs behind it — allowlisting
    the page must not have opened anything else, including the trigger
    endpoints the page's controls call."""
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    for method, path in (
        ("get", "/v1/itinerary/status/some-trip"),
        ("get", "/v1/itinerary/trips"),
        ("get", "/v1/sabre_tools/latest_trip_id"),
        ("post", "/v1/demo/book"),
        ("post", "/v1/demo/disrupt"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


# --- page content: consolidated frame & repair surfaces -------------------------


def page_text():
    return client.get("/v1/cascade/").text


def test_page_is_self_contained():
    """No external requests — inline CSS/JS only, per the no-dependency rule."""
    text = page_text()
    assert 'src="http' not in text and 'href="http' not in text


def test_page_contains_all_status_visual_hooks():
    """Every status in the repair lifecycle has a visual on the page — the
    six-status treatment on the flight card, reservation cards, and
    timeline legs."""
    text = page_text()
    for status in ("planned", "booked", "broken", "repairing", "fixed", "cancelled"):
        assert f'[data-status="{status}"]' in text


def test_page_carries_the_mockup_frame():
    """The booking frame's surfaces survive the clone: app header with
    current traveler + status pill, left-rail traveler context, trip
    timeline, collapsible recent trips, the prominent current-flight card,
    and the reservations."""
    text = page_text()
    for surface in (
        "Current Traveler", "Traveler Context", "Trip Timeline",
        "Recent Trips", "Current Flight", "The Rest of the Trip",
    ):
        assert surface in text


def test_page_carries_the_repair_surfaces():
    """Phase 22's additions: recovery banner copy, the 60-second recovery
    timer, the disruption score chip, and the downstream-impact panel."""
    text = page_text()
    assert "Cascade is actively repairing your itinerary" in text
    assert "TARGET_S = 60" in text and "60s target" in text
    assert "Disruption Score" in text
    for band in ("Minimal", "Moderate", "Severe"):
        assert band in text
    assert "Downstream Impact" in text
    # The impact dot's two states, keyed off the detail payload.
    assert "Adjusted" in text and "price_delta" in text and "detail.impact" in text


def test_page_derives_the_score_client_side():
    """The score is a documented client-side heuristic over the status
    payload — no backend field: broken/repairing weights, price drift,
    elapsed-vs-target, clamped to 0–100."""
    text = page_text()
    assert "function disruptionScore" in text
    assert "Math.min(100" in text  # the clamp
    # The documented weights: broken dominates, repairing half, price drift
    # and elapsed-vs-target capped.
    assert "+= 28" in text and "+= 14" in text
    assert "Math.min(20, drift" in text


def test_page_has_the_trigger_controls_wired_to_the_demo_orchestrator():
    """Both beats fire from this page: Book → POST /v1/demo/book (pinning
    the returned trip immediately) and Cancel flight → cascade →
    POST /v1/demo/disrupt with the pinned trip. Markup-only assertion —
    the endpoints are never called here."""
    text = page_text()
    assert "/v1/demo/book" in text
    assert "/v1/demo/disrupt" in text
    assert 'id="btn-book"' in text and 'id="btn-cancel"' in text
    # Book pins the returned trip_id without waiting on latest_trip_id.
    assert "resetForTrip(body.trip_id)" in text
    # Disrupt targets the pinned trip and stays disabled until one exists.
    assert "trip_id: tripId" in text
    assert "!state.tripId" in text
    # Errors (503 locally, 502 on a failed call) surface inline, scrubbed
    # upstream — the page never renders callee/env fields of its own.
    assert "errorFrom" in text
    assert "body.error || body.detail" in text


def test_page_center_column_is_the_phase_23_voice_placeholder():
    """The center slot is reserved and clearly labeled — no VB CDN imports,
    no token fetch, no voice wiring of any kind."""
    text = page_text()
    assert 'id="voice-placeholder"' in text
    assert "Phase 23" in text
    for absent in ("vbConnect", "useAIAgent", "/v1/web_call", "token",
                   "cdn", "webrtc", "getUserMedia"):
        assert absent not in text, absent


def test_page_renders_times_pacific_labeled_pt():
    """Every rendered clock time is America/Los_Angeles, labeled "PT" —
    never "PST" (it's PDT in July), never browser-local."""
    text = page_text()
    assert 'timeZone: "America/Los_Angeles"' in text
    assert '" PT"' in text
    assert "PST" not in text


def test_page_rounds_prices_like_the_concierge_speaks():
    assert "Math.round" in page_text()


def test_page_polls_status_on_the_shared_cadence():
    text = page_text()
    assert "POLL_MS = 1500" in text
    assert "/v1/itinerary" in text and "/status/" in text


def test_page_honors_the_trip_pinning_contract():
    """?trip_id= seeds the displayed trip and window.vbSetTrip repoints it —
    the web_call/mobile_voice contract — and latest_trip_id re-resolution
    adopts a trip booked mid-conversation without a reload."""
    text = page_text()
    assert 'searchParams.get("trip_id")' in text
    assert "window.vbSetTrip" in text
    assert "latest_trip_id" in text


def test_page_has_access_code_wiring():
    text = page_text()
    assert 'searchParams.get("code")' in text
    assert "vb_access_code" in text
    assert "X-Access-Code" in text


def test_page_recent_trips_sorted_newest_first_with_created_labels():
    text = page_text()
    assert "fmtCreated(trip.created_at)" in text
    assert "trips.sort" in text and "b.created_at" in text


def test_page_has_an_awaiting_state():
    text = page_text()
    assert 'id="awaiting"' in text
    assert "Awaiting trip" in text


def test_page_renders_pending_options_as_the_candidates_panel():
    """The booking beat survives on this page: the mockup's "AI Recommended"
    card, fed by the status payload's pending_options block."""
    text = page_text()
    assert 'id="candidates"' in text
    assert "AI Recommended" in text
    assert "pending_options" in text
    for field in ("option_number", "arrive_time", "depart_time",
                  "route", "stops"):
        assert f"o.{field}" in text, field
    assert "fmtPrice(o.price)" in text
