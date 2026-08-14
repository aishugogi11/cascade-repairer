"""Fake WhatsApp Cascade front door — hermetic (no GCP, no network)."""
from fastapi.testclient import TestClient

import main
from api import whatsapp_demo

client = TestClient(main.app)
CODE = "demo-code-1234"


def test_shell_is_public_when_gate_armed(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    resp = client.get("/v1/whatsapp/")
    assert resp.status_code == 200
    assert "Cascade Repairer — WhatsApp" in resp.text
    assert "Not live WhatsApp" in resp.text
    assert "/v1/whatsapp/ingest" in resp.text
    assert "cascade_path" in resp.text or "data.cascade_path" in resp.text
    assert "X-Access-Code" in resp.text
    assert "vb_access_code" in resp.text
    assert 'searchParams.get("code")' in resp.text
    assert "data.detail" in resp.text
    assert "pdf_base64" in resp.text
    assert "Check the access code and try again" not in resp.text


def test_ingest_is_gated(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    resp = client.post("/v1/whatsapp/ingest", json={"sample": True})
    assert resp.status_code == 401


def test_ingest_falls_back_without_bigquery(monkeypatch):
    from fastapi import HTTPException
    from api import memory_trips
    memory_trips.clear()
    monkeypatch.setenv("K_SERVICE", "test")
    monkeypatch.setattr(
        whatsapp_demo,
        "create_seed_trip",
        lambda user_id, title: (_ for _ in ()).throw(HTTPException(status_code=500, detail="no adc")),
    )
    resp = client.post("/v1/whatsapp/ingest", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "memory"
    trip_id = body["trip_id"]
    status = client.get("/v1/itinerary/status/" + trip_id)
    assert status.status_code == 200
    assert status.json()["trip"]["trip_id"] == trip_id
    assert len(status.json()["items"]) == 5
    memory_trips.clear()


def test_ingest_skips_bigquery_without_credentials(monkeypatch):
    from api import memory_trips
    memory_trips.clear()
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    def boom(user_id, title):
        raise AssertionError("should not wait on BigQuery without credentials")

    monkeypatch.setattr(whatsapp_demo, "create_seed_trip", boom)
    resp = client.post("/v1/whatsapp/ingest", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "memory"
    assert body["trip_id"]
    memory_trips.clear()


def test_ingest_seeds_cascade_trip(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "test")
    monkeypatch.setattr(
        whatsapp_demo,
        "create_seed_trip",
        lambda user_id, title: {
            "trip_id": "wa-trip-1",
            "items": [
                {"type": "flight"},
                {"type": "hotel"},
                {"type": "ground"},
                {"type": "dining"},
                {"type": "experience"},
            ],
        },
    )
    resp = client.post("/v1/whatsapp/ingest", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["demo"] is True
    assert body["source"] == "bigquery"
    assert body["trip_id"] == "wa-trip-1"
    assert body["cascade_path"] == "/v1/cascade/?trip_id=wa-trip-1"
    assert "1 flight" in body["spoken_counts"]
    assert "1 hotel" in body["spoken_counts"]
    assert "Talk" in body["reply_done"]
    assert "reviewing" in body["reply_reviewing"].lower()


def test_ingest_sample_builds_pdf_itinerary():
    from api import memory_trips
    memory_trips.clear()
    resp = client.post("/v1/whatsapp/ingest", json={"sample": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "sample"
    status = client.get("/v1/itinerary/status/" + body["trip_id"]).json()
    titles = [
        (i.get("details") or {}).get("title") or i.get("location") or ""
        for i in status["items"]
    ]
    blob = " ".join(titles)
    assert any("Golden Gate" in t or "Bridge" in t for t in titles)
    assert any("Chase" in t or "Concert" in t for t in titles)
    assert "hotel" in {i["type"] for i in status["items"]}
    assert "dining" in {i["type"] for i in status["items"]}
    assert "SFO" in blob or any(i["type"] == "ground" for i in status["items"])
    latest = client.get("/v1/sabre_tools/latest_trip_id")
    assert latest.status_code == 200
    assert latest.json()["trip_id"] == body["trip_id"]
    listed = client.get("/v1/itinerary/trips")
    assert listed.status_code == 200
    assert listed.json()["trips"][0]["trip_id"] == body["trip_id"]
    memory_trips.clear()


def test_ingest_pdf_bytes_match_uploaded_itinerary():
    import base64
    from pathlib import Path
    from api import memory_trips
    memory_trips.clear()
    pdf = Path(__file__).resolve().parents[1] / "api" / "assets" / "build" / "sample_tripwise_itinerary.pdf"
    payload = {
        "sample": False,
        "filename": "alex-morgan.pdf",
        "pdf_base64": base64.b64encode(pdf.read_bytes()).decode("ascii"),
    }
    resp = client.post("/v1/whatsapp/ingest", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "pdf"
    status = client.get("/v1/itinerary/status/" + body["trip_id"]).json()
    titles = [
        (i.get("details") or {}).get("title") or ""
        for i in status["items"]
    ]
    assert any("Golden Gate" in t or "Bridge" in t for t in titles)
    memory_trips.clear()


def test_ingest_flight_confirmation_text_makes_a_flight_row():
    from api import memory_trips
    memory_trips.clear()
    text = (
        "Saturday, August 22, 2026\n"
        "DL 439 MSP-SFO departs 8:00 AM arrives 12:05 PM\n"
        "08:00 Breakfast — Union Square\n"
        "18:00 Dinner — Mission District\n"
    )
    resp = client.post("/v1/whatsapp/ingest", json={"text": text, "filename": "eticket.pdf"})
    assert resp.status_code == 200
    items = client.get("/v1/itinerary/status/" + resp.json()["trip_id"]).json()["items"]
    flights = [i for i in items if i["type"] == "flight"]
    assert flights
    assert flights[0]["details"]["airline"] == "DL"
    assert flights[0]["details"]["flight_number"] == 439
    assert flights[0]["location"] == "MSP-SFO"
    memory_trips.clear()
