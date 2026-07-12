"""Voice booking page tests — Phase 21, hermetic (no GCP, no network).

Run against the real main.app so the router registration and the
access-gate allowlisting are both under test — the page shell must stay
reachable without a code while the JSON endpoints it polls stay gated.
"""
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

CODE = "demo-code-1234"


def test_shell_served_without_code_when_gate_armed(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    resp = client.get("/v1/booking/")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Voice Booking — Cascade Repairer" in resp.text


def test_gated_json_endpoints_still_401_without_code(monkeypatch):
    """The shell is inert without the gated APIs behind it — allowlisting
    the page must not have opened anything else."""
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    for path in (
        "/v1/itinerary/status/some-trip",
        "/v1/itinerary/trips",
        "/v1/sabre_tools/latest_trip_id",
    ):
        resp = client.get(path)
        assert resp.status_code == 401, path


# --- page content: mockup frame & reservation display --------------------------


def page_text():
    return client.get("/v1/booking/").text


def test_page_is_self_contained():
    """No external requests — inline CSS/JS only, per the no-dependency rule."""
    text = page_text()
    assert 'src="http' not in text and 'href="http' not in text


def test_page_contains_all_status_visual_hooks():
    """Every status in the repair lifecycle has a visual on the page — the
    six-status card treatment the later disruption phases rely on."""
    text = page_text()
    for status in ("planned", "booked", "broken", "repairing", "fixed", "cancelled"):
        assert f'[data-status="{status}"]' in text


def test_page_carries_the_mockup_frame():
    """The mockup's surfaces: app header with current traveler + status pill,
    left-rail traveler context, trip timeline, collapsible recent trips, and
    the prominent current-flight card."""
    text = page_text()
    for surface in (
        "Current Traveler", "Traveler Context", "Trip Timeline",
        "Recent Trips", "Current Flight", "The Rest of the Trip",
    ):
        assert surface in text
    # Booking-beat pill states.
    assert "Booking by voice" in text and "Trip confirmed" in text


def test_page_renders_times_pacific_labeled_pt():
    """Card times and the recent-trips created-at label render
    America/Los_Angeles for every viewer, labeled "PT" — never "PST"
    (it's PDT in July), never browser-local."""
    text = page_text()
    assert text.count('timeZone: "America/Los_Angeles"') == 2
    assert text.count('" PT"') == 2
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


def test_page_recent_trips_sorted_newest_first_with_created_labels():
    text = page_text()
    assert "fmtCreated(trip.created_at)" in text
    assert "trips.sort" in text and "b.created_at" in text


def test_page_has_an_awaiting_state():
    text = page_text()
    assert 'id="awaiting"' in text
    assert "Awaiting trip" in text


# --- candidate options panel ---------------------------------------------------


def test_page_renders_pending_options_as_the_candidates_panel():
    """The mockup's "AI Recommended" card treatment, fed by the status
    payload's pending_options block: numbered options, PT-labeled times,
    route and stops — matching what the Concierge speaks."""
    text = page_text()
    assert 'id="candidates"' in text
    assert "AI Recommended" in text
    assert "pending_options" in text
    for field in ("option_number", "arrive_time", "depart_time",
                  "route", "stops"):
        assert f"o.{field}" in text, field
    # Prices go through the same rounded formatter as the cards.
    assert "fmtPrice(o.price)" in text


def test_page_clears_the_candidates_panel_when_the_block_disappears():
    """Booking happened: the panel empties and hides, and the booked flight
    arrives through the normal items path — the visual hand-off."""
    text = page_text()
    assert 'classList.toggle("has-candidates"' in text
    assert "renderCandidates(body.pending_options)" in text
    # The awaiting state never shows candidates (no trip displayed).
    assert "renderCandidates(null)" in text
