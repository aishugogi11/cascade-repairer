"""Legal-page tests — Phase 16, hermetic (static HTML, no GCP, no network).

The router is mounted on a local app per test_itinerary_ui.py conventions;
main.py wiring has its own smoke test. The content assertions pin what App
Store review actually checks: the privacy page covers microphone/audio
processing and offers a contact, the support page links back to the privacy
page.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.legal import legal

app = FastAPI()
app.include_router(legal, prefix="/v1/legal")


def test_privacy_page_serves_html():
    with TestClient(app) as client:
        resp = client.get("/v1/legal/privacy")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


def test_privacy_page_covers_microphone_and_contact():
    with TestClient(app) as client:
        text = client.get("/v1/legal/privacy").text.lower()

    assert "microphone" in text
    assert "audio" in text
    assert "vocal bridge" in text
    assert "transcripts" in text
    assert "mailto:" in text


def test_support_page_serves_html():
    with TestClient(app) as client:
        resp = client.get("/v1/legal/support")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


def test_support_page_links_to_privacy_and_offers_contact():
    with TestClient(app) as client:
        text = client.get("/v1/legal/support").text

    assert "/v1/legal/privacy" in text
    assert "mailto:" in text


def test_pages_are_self_contained():
    """No external requests — scripts, styles, and images all inline."""
    with TestClient(app) as client:
        for path in ("/v1/legal/privacy", "/v1/legal/support"):
            text = client.get(path).text
            assert "http://" not in text
            assert "https://" not in text
            assert "<script" not in text
