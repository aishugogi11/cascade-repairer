"""Headless mobile-voice page tests — Phase 16, hermetic (static HTML, no
GCP, no network; page JS behavior is scripted manual QA per the standing
no-browser-automation decision).

The load-bearing contracts: the native bridge surface exists (vbConnect /
vbDisconnect / messageHandlers.vb), the spoken turns still delegate to the
proven /v1/web_call/query seam, and the page is genuinely headless — no
visible UI for a 4.2 webview-wrapper rejection to point at.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import web_call
from api.mobile_voice import mobile_voice

app = FastAPI()
app.include_router(mobile_voice, prefix="/v1/mobile_voice")


def _page_text():
    with TestClient(app) as client:
        resp = client.get("/v1/mobile_voice/")
    return resp


def test_page_serves_html():
    resp = _page_text()
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


def test_page_exposes_native_bridge_surface():
    text = _page_text().text
    assert "vbConnect" in text
    assert "vbDisconnect" in text
    assert "messageHandlers.vb" in text


def test_page_delegates_queries_to_web_call():
    text = _page_text().text
    assert "/v1/web_call/query" in text
    assert "/v1/web_call/token" in text


def test_page_posts_all_event_types():
    text = _page_text().text
    for event in ("'state'", "'transcript'", "'reply'", "'error'"):
        assert f"type: {event}" in text


def test_page_is_headless():
    text = _page_text().text
    assert "<button" not in text
    assert "<h1" not in text
    assert 'style="display:none"' in text


def test_page_pins_the_web_call_cdn_versions():
    """Same VB stack as the proven browser surface — versions can't drift."""
    text = _page_text().text
    assert f"@vocalbridgeai/react@{web_call.VB_REACT_VER}" in text
    assert f"react@{web_call.REACT_VER}" in text


def test_page_carries_the_trip_pin_wiring():
    """Phase 19: ?trip_id= and window.vbSetTrip (native's hook) feed trip_id
    into the /query POST so the session pins the displayed trip."""
    text = _page_text().text
    assert "vbSetTrip" in text
    assert "trip_id" in text


def test_page_temp_bridge_self_resolves_latest_trip():
    """The TEMP bridge for the in-review binary: the page fetches
    latest_trip_id itself (access-code headers, lowest precedence) and is
    marked in-code for removal when native vbSetTrip ships in v1.0.1."""
    text = _page_text().text
    assert "/v1/sabre_tools/latest_trip_id" in text
    assert "TEMP bridge" in text
    assert "v1.0.1" in text
