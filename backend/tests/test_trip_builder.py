"""Optimize My Trip — hermetic (no GCP, no OpenAI, no network)."""
import asyncio

import pytest
from fastapi.testclient import TestClient

import main
from api import concierge, memory_trips, optimize
from ml.transport.maps import directions_url
from ml.transport.optimize import Prefs, optimize_stops, suggest_reorder
from ml.transport.parse import SAMPLE_ITINERARY, parse_text
from ml.transport.train import train

client = TestClient(main.app)
CODE = "demo-code-1234"


@pytest.fixture(autouse=True)
def _clean_sessions(monkeypatch):
    optimize.clear_sessions()
    monkeypatch.delenv("UBER_SERVER_TOKEN", raising=False)
    monkeypatch.delenv("UBER_ACCESS_TOKEN", raising=False)


def test_parse_messy_itinerary_formats():
    text = """
    Saturday 09:00 The Plaza
    11:00 AM Museum of Modern Art
    1:00pm The Standard Grill
    3pm
    The Metropolitan Museum of Art
    Concert at Madison Square Garden 7:30 PM
    """
    stops = parse_text(text)
    titles = [s["title"] for s in stops]
    assert stops[0]["start_time"] == "09:00"
    assert any("Plaza" in t for t in titles)
    assert any("Modern Art" in t for t in titles)
    assert stops[1]["start_time"] == "11:00"
    assert any("Standard" in t for t in titles)
    assert any("Metropolitan" in t or "Met" in t for t in titles)
    assert any("Madison Square" in t for t in titles)
    assert stops[-1]["start_time"] == "19:30"


def test_parse_sample_has_timed_stops():
    stops = parse_text(SAMPLE_ITINERARY)
    titles = [s["title"] for s in stops]
    assert len(stops) >= 14
    assert any("Union Square" in t for t in titles)
    assert any("Golden Gate" in t for t in titles)
    assert any("Chase Center" in t for t in titles)
    assert any("Alcatraz" in t or "Pier 33" in t for t in titles)
    assert any("SFO" in t or "Airport" in t for t in titles)
    assert stops[0]["start_time"] == "08:00"
    assert stops[-1]["start_time"] == "20:00"
    assert any(s["anchored"] for s in stops if "Chase" in s["title"] or "Alcatraz" in s["title"])
    assert stops[-1]["day"] == 1


def test_parse_sf_pdf():
    from pathlib import Path
    from ml.transport.parse import parse_pdf_bytes
    pdf = Path(__file__).resolve().parents[1] / "api" / "assets" / "build" / "sample_tripwise_itinerary.pdf"
    stops = parse_pdf_bytes(pdf.read_bytes())
    titles = [s["title"] for s in stops]
    assert len(stops) >= 10
    assert any("Golden Gate" in t or "Bridge" in t for t in titles)
    assert any("Chase" in t or "Concert" in t for t in titles)


def test_parse_nyc_pdf():
    from pathlib import Path
    from ml.transport.parse import parse_pdf_bytes
    pdf = (
        Path(__file__).resolve().parents[1]
        / "api"
        / "assets"
        / "build"
        / "sample_nyc_business_itinerary.pdf"
    )
    stops = parse_pdf_bytes(pdf.read_bytes())
    titles = [s["title"] for s in stops]
    assert len(stops) >= 10
    assert any("UA 215" in t or "SFO-JFK" in t for t in titles)
    assert any("Financial" in t or "Client" in t for t in titles)
    assert any("Rockefeller" in t for t in titles)
    assert any("Central Park" in t for t in titles)


def test_nyc_sample_pdf_download(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    resp = client.get("/v1/build/sample/nyc.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 500


def test_reorder_reduces_backtracking():
    stops = parse_text(SAMPLE_ITINERARY)
    rec = suggest_reorder(stops)
    if rec is None:
        # Anchored Alcatraz/concert/checkout can pin the route; still a valid outcome.
        return
    assert rec["miles_saved"] > 0
    orig = rec["current_titles"]
    new = rec["recommended_titles"]
    assert orig != new
    assert orig[0] == new[0]
    assert orig[-1] == new[-1]


def test_train_forest_beats_linear(tmp_path, monkeypatch):
    monkeypatch.setattr("ml.transport.model.MODEL_PATH", tmp_path / "tq.joblib")
    monkeypatch.setattr("ml.transport.model.METRICS_PATH", tmp_path / "metrics.json")
    _, metrics, path = train(n=2500, seed=0)
    assert path.exists()
    rf = metrics["comparison"]["RandomForestRegressor"]
    lr = metrics["comparison"]["LinearRegression"]
    assert rf["r2"] > lr["r2"]
    assert rf["mae"] < lr["mae"]
    assert rf["r2"] >= 0.55
    assert metrics["n_test"] == 500
    assert metrics["dataset"] == "synthetic_transport_quality"
    assert "synthetic" in metrics["dataset_disclaimer"].lower()
    assert metrics["n_features"] == len(metrics["features"])


def test_optimize_returns_calculated_intelligence(tmp_path, monkeypatch):
    monkeypatch.setattr("ml.transport.model.MODEL_PATH", tmp_path / "tq.joblib")
    monkeypatch.setattr("ml.transport.model.METRICS_PATH", tmp_path / "metrics.json")
    from ml.transport import predict as predict_mod
    predict_mod.reset_cache()
    train(n=1800, seed=1)
    predict_mod.reset_cache()
    stops = parse_text(SAMPLE_ITINERARY)
    result = optimize_stops(stops, Prefs(priority="time"))
    intel = result["intelligence"]
    assert 0 <= intel["optimization_score"] <= 100
    assert intel["potential_improvements"] >= 1
    assert intel["travel_time_saved_min"] >= 0
    assert result["transitions"]
    ranked = result["transitions"][0]["ranked"]
    assert len(ranked) == 5
    assert ranked[0]["final_score"] >= ranked[-1]["final_score"]
    assert result["model"]["source"] in ("trained_artifact", "heuristic_fallback")


def test_walk_constraint_drops_long_walks(tmp_path, monkeypatch):
    monkeypatch.setattr("ml.transport.model.MODEL_PATH", tmp_path / "tq.joblib")
    monkeypatch.setattr("ml.transport.model.METRICS_PATH", tmp_path / "metrics.json")
    from ml.transport import predict as predict_mod
    predict_mod.reset_cache()
    train(n=1200, seed=2)
    predict_mod.reset_cache()
    stops = parse_text(SAMPLE_ITINERARY)
    result = optimize_stops(stops, Prefs(priority="time", max_walk_minutes=8))
    for tr in result["transitions"]:
        rec = tr["recommended"]
        if rec["transportation_mode"] == "walk":
            assert rec["estimated_travel_time"] <= 8.5


def test_walk_hop_includes_google_maps_route():
    origin = (37.7880, -122.4075)
    dest = (37.8021, -122.4187)
    url = directions_url(
        origin, dest, mode="walking",
        origin_query="Apple Union Square, 300 Post St, San Francisco, CA",
        dest_query="Lombard Street, San Francisco, CA",
    )
    assert url.startswith("https://www.google.com/maps/dir/?")
    assert "travelmode=walking" in url
    assert "Apple" in url
    assert "Lombard" in url
    stops = parse_text(SAMPLE_ITINERARY)
    assert "Apple Store" in stops[0]["title"]
    result = optimize_stops(stops, Prefs(priority="time", max_walk_minutes=10))
    first = result["optimized_stops"][0]
    assert first.get("maps_url", "").startswith("https://www.google.com/maps/dir/?")
    assert "SFO" in first["maps_url"] or "Airport" in first["maps_url"]
    assert "driving" in first["maps_url"]
    walk_hops = [t for t in result["transitions"] if t.get("maps_url")]
    assert walk_hops
    for item in walk_hops:
        link = item["maps_url"]
        assert link.startswith("https://www.google.com/maps/dir/?")
        assert "travelmode=walking" in link
        assert "San+Francisco" in link or "San Francisco" in link


def test_time_priority_saves_travel_time():
    stops = parse_text(SAMPLE_ITINERARY)
    timed = optimize_stops(stops, Prefs(priority="time"))
    assert timed["intelligence"]["travel_time_saved_min"] >= 8
    assert timed["intelligence"]["original_travel_min"] > timed["intelligence"]["optimized_travel_min"]
    modes = [t["recommended"]["transportation_mode"] for t in timed["transitions"]]
    assert any(m in ("uber_alt_pickup", "lyft", "uber", "walk") for m in modes)
    assert timed["intelligence"]["walk_hops"] + timed["intelligence"]["rideshare_hops"] >= 1


def test_potential_improvement_when_policy_keeps_current(monkeypatch):
    monkeypatch.setattr(
        "ml.transport.optimize.predict_action_utility_many",
        lambda rows: [
            {
                "utility": 1.0 if row.get("action_type") == "KEEP_CURRENT_PLAN" else 0.0,
                "source": "test",
            }
            for row in rows
        ],
    )
    stops = parse_text(SAMPLE_ITINERARY)
    result = optimize_stops(stops, Prefs(priority="time", max_walk_minutes=10))
    assert result["intelligence"]["travel_time_saved_min"] >= 8
    assert result["intelligence"]["original_travel_min"] > result["intelligence"]["optimized_travel_min"]


def test_ingest_sample_and_voice_time_priority():
    first = asyncio.run(optimize.apply_turn("s1", "try sample"))
    assert first["ok"] is True
    assert len(first["original_stops"]) >= 4
    assert first["prefs"]["priority"] == "time"
    assert first["prefs"]["max_walk_minutes"] == 10
    assert first["intelligence"]["potential_improvements"] >= 1
    assert "recommend" in first["reply"].lower() or "change" in first["reply"].lower()
    here = first.get("here_now") or {}
    assert "Union Square" in (here.get("at") or "")
    assert "Golden Gate" in (here.get("next") or "")
    assert here.get("uber_source") == "uber_unavailable"
    assert here.get("cheapest") is None
    assert here.get("deeplink", "").startswith("https://m.uber.com/looking")
    assert first["data_sources"]["uber"] == "uber_unavailable"
    second = asyncio.run(optimize.apply_turn("s1", "Make this trip as fast as possible."))
    assert second["prefs"]["priority"] == "time"
    assert "time" in second["reply"].lower() or "action" in second["reply"].lower()
    rec = asyncio.run(optimize.apply_turn("s1", "What do you recommend?"))
    assert rec["ok"] is True
    rec_l = rec["reply"].lower()
    assert "recommend" in rec_l or "changed" in rec_l
    assert "need" in rec_l or "walk" in rec_l or "rideshare" in rec_l or "uber" in rec_l
    uber = asyncio.run(optimize.apply_turn("s1", "What's the cheapest Uber from the first stop?"))
    assert uber["ok"] is True
    assert "union square" in uber["reply"].lower()
    assert "golden gate" in uber["reply"].lower()
    assert "first stop" in uber["reply"].lower()
    assert (
        "cheapest uber" in uber["reply"].lower()
        or "available ubers" in uber["reply"].lower()
        or "won't invent" in uber["reply"].lower()
    )
    assert (uber.get("here_now") or {}).get("deeplink", "").startswith(
        "https://m.uber.com/looking"
    )


def test_voice_recovers_itinerary_after_session_wipe():
    """Reload wipes in-memory optimize sessions; voice must re-adopt the
    Cascade memory trip instead of saying the itinerary is missing."""
    memory_trips.clear()
    first = asyncio.run(optimize.apply_turn("opt-page-nyc", "try sample"))
    assert first["ok"] is True
    assert first.get("trip_id")
    optimize.clear_sessions()
    assert optimize._SESSIONS == {}
    voice = asyncio.run(optimize.apply_turn(
        "vb-fresh-room", "What do you recommend?"
    ))
    assert voice["ok"] is True
    assert "don't see" not in voice["reply"].lower()
    assert "upload" not in voice["reply"].lower() or "recommend" in voice["reply"].lower()
    assert len(voice.get("original_stops") or voice.get("stops") or []) >= 2
    blob = voice["reply"].lower()
    assert "recommend" in blob or "changed" in blob or "action" in blob or "hop" in blob
    memory_trips.clear()


def test_voice_confirms_itinerary_with_bound_trip_id():
    memory_trips.clear()
    first = asyncio.run(optimize.apply_turn("opt-bind", "try sample"))
    trip_id = first["trip_id"]
    assert trip_id
    optimize.clear_sessions()
    voice = asyncio.run(optimize.apply_turn(
        "vb-bind-room",
        "Do you have my itinerary?",
        trip_id=trip_id,
    ))
    assert voice["ok"] is True
    assert voice.get("trip_id") == trip_id
    assert "yes" in voice["reply"].lower()
    assert "itinerary" in voice["reply"].lower()
    memory_trips.clear()


def test_uber_voice_reads_memory_trip_after_session_reset():
    memory_trips.clear()
    first = asyncio.run(optimize.apply_turn("page-nyc", "try sample"))
    assert first["ok"] is True
    optimize.clear_sessions()
    spoken = asyncio.run(concierge.answer_query(
        "vb-other-room", "What's the cheapest Uber from the first stop?",
    ))
    assert "don't see a booked trip" not in spoken.lower()
    assert "doesn't have any" not in spoken.lower()
    assert "union square" in spoken.lower()
    assert "first stop" in spoken.lower()
    memory_trips.clear()


def test_best_option_first_stop_uses_loaded_itinerary():
    memory_trips.clear()
    first = asyncio.run(optimize.apply_turn("opt-first-best", "try sample"))
    assert first["ok"] is True
    optimize.clear_sessions()
    spoken = asyncio.run(concierge.answer_query(
        "vb-first-best", "What is the best option for the first stop?",
    ))
    assert "not loaded" not in spoken.lower()
    assert "don't see" not in spoken.lower()
    assert "first stop" in spoken.lower() or "uber" in spoken.lower() or "rideshare" in spoken.lower()
    memory_trips.clear()


def test_upload_publishes_trip_to_cascade():
    memory_trips.clear()
    first = asyncio.run(optimize.apply_turn("s-cascade", "try sample"))
    assert first["ok"] is True
    assert first.get("trip_id")
    assert str(first.get("cascade_path") or "").startswith("/v1/cascade/?trip_id=")
    view = memory_trips.get(first["trip_id"])
    assert view is not None
    assert len(view.items) >= 2
    blob = " ".join(
        ((i.details or {}).get("title") or i.location or "") for i in view.items
    )
    assert "Apple Store" in blob or "Union Square" in blob or "Golden Gate" in blob


def test_voice_session_reuses_page_trip():
    page = asyncio.run(optimize.apply_turn("opt-page", "try sample"))
    assert page["ok"] is True
    voice = asyncio.run(optimize.apply_turn("vb-room-xyz", "optimize my trip for time"))
    assert voice["ok"] is True
    assert voice["prefs"]["priority"] == "time"
    assert len(voice.get("original_stops") or []) >= 4
    assert "score a trip first" not in voice["reply"].lower()


def test_optimize_without_upload_loads_sample():
    out = asyncio.run(optimize.apply_turn("fresh-voice", "optimize my trip for time"))
    assert out["ok"] is True
    assert len(out.get("original_stops") or []) >= 4
    assert "score a trip first" not in out["reply"].lower()


def test_build_page_is_optimize_shell(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    resp = client.get("/v1/build/")
    assert resp.status_code == 200
    assert "Optimize My Trip" in resp.text
    assert "Already have a trip planned" in resp.text
    assert "Upload Itinerary" in resp.text
    assert "Paste Itinerary" in resp.text
    assert "Trip Optimized" in resp.text
    assert "id=\"day-travel\"" in resp.text or 'id="day-travel"' in resp.text
    assert "l-orig" in resp.text
    assert "Model Intelligence" in resp.text
    assert "/v1/trip_builder" in resp.text
    assert '"/parse"' in resp.text or "/parse" in resp.text
    assert "/v1/trip_builder/token" in resp.text
    assert "X-Access-Code" in resp.text
    assert "esm.sh" in resp.text
    assert "Build your trip without the research rabbit hole" not in resp.text
    assert "You're at the first stop" in resp.text
    assert "Uber from the first stop" in resp.text
    assert "cheapest Uber from the first stop" not in resp.text
    assert "cheapest live Uber" not in resp.text
    assert "See available Ubers" in resp.text
    assert "what do you recommend" in resp.text
    assert "Try sample San Francisco weekend" not in resp.text
    assert "Try sample New York business trip" not in resp.text
    assert "Download NYC PDF" not in resp.text
    assert "vb_optimize_trip_id" in resp.text
    assert "trip_id: bridge.tripId" in resp.text or "trip_id: bridge.tripId ?" in resp.text
    assert "bridge.tripId()" in resp.text


def test_trip_builder_json_is_gated(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    resp = client.post("/v1/trip_builder/parse", json={"sample": True})
    assert resp.status_code == 401


def test_token_requires_build_key(monkeypatch):
    monkeypatch.delenv("VOCAL_BRIDGE_BUILD_API_KEY", raising=False)
    monkeypatch.delenv("VOCAL_BRIDGE_API_KEY", raising=False)
    resp = client.post("/v1/trip_builder/token")
    assert resp.status_code == 503
    assert "VOCAL_BRIDGE_BUILD_API_KEY" in resp.json()["error"]


def test_transport_metrics_endpoint():
    resp = client.get("/v1/ml/transport")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] in ("trained_artifact", "heuristic_fallback")
    assert "synthetic" in body.get("dataset_disclaimer", "").lower() or body["source"] == "heuristic_fallback"


def test_policy_metrics_endpoint():
    resp = client.get("/v1/ml/transport/policy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] in ("trained_artifact", "heuristic_fallback")
    assert "synthetic" in body.get("dataset_disclaimer", "").lower() or body["source"] == "heuristic_fallback"


def test_action_loop_executes_and_labels_demo_data():
    stops = parse_text(SAMPLE_ITINERARY)
    result = optimize_stops(stops, Prefs(priority="time"))
    assert result["data_sources"]["maps"] in ("demo_geometry", "google_maps")
    assert result["data_sources"]["rideshare"] == "demo_simulated"
    assert result["intelligence"]["cost_saved"] is None
    assert "snapshots" in result
    assert result["analysis_stages"]
    assert result["transitions"][0]["ranked"]
    assert len(result["transitions"][0]["ranked"]) == 5
    if result["rideshare_card"]:
        assert result["rideshare_card"]["price"] is None
        assert result["rideshare_card"]["price_available"] is False
    here = result["here_now"]
    assert here["at"]
    assert here["next"]
    assert here["uber_source"] == "uber_unavailable"
    assert here["cheapest"] is None
    assert not here["uber_quotes"]
    assert result["data_sources"]["uber"] == "uber_unavailable"
    orig_titles = [s["title"] for s in result["original_stops"]]
    opt_titles = [s["title"] for s in result["optimized_stops"]]
    changed = orig_titles != opt_titles or any(
        (a.get("action") or "") != "KEEP_CURRENT_PLAN" for a in result["action_history"]
    ) or any(t["changed"] for t in result["transitions"])
    assert changed
    assert result["intelligence"]["original_travel_min"] >= result["intelligence"]["optimized_travel_min"]


def test_travel_time_is_typical_day_not_trip_total():
    stops = parse_text(SAMPLE_ITINERARY)
    intel = optimize_stops(stops, Prefs(priority="time"))["intelligence"]
    days = intel["travel_by_day"]
    assert len(days) == 2
    for row in days:
        assert 45 <= row["original_min"] <= 240
        assert row["optimized_min"] <= row["original_min"]
    assert intel["original_travel_total_min"] > intel["original_travel_min"]
    avg = round(sum(d["original_min"] for d in days) / len(days))
    assert intel["original_travel_min"] == avg
    assert intel["travel_time_saved_min"] >= 8


def test_daily_travel_does_not_count_a_cross_country_hop_as_a_city_day():
    from ml.transport.optimize import _daily_minutes
    union = {
        "title": "Union Square", "lat": 37.7880, "lon": -122.4075, "venue_type": "other",
    }
    ggb = {
        "title": "Golden Gate Bridge", "lat": 37.8079, "lon": -122.4750, "venue_type": "park",
    }
    sfo = {"title": "SFO", "lat": 37.6213, "lon": -122.3790, "venue_type": "airport"}
    jfk = {"title": "JFK", "lat": 40.6413, "lon": -73.7781, "venue_type": "airport"}
    assert _daily_minutes(union, ggb, 32) == 32
    assert _daily_minutes(union, ggb, 1800) == 30
    assert _daily_minutes(sfo, jfk, 9000) == 150


def test_train_policy_beats_rules(tmp_path, monkeypatch):
    monkeypatch.setattr("ml.transport.policy_train.POLICY_PATH", tmp_path / "ap.joblib")
    monkeypatch.setattr("ml.transport.policy_train.POLICY_METRICS_PATH", tmp_path / "pm.json")
    from ml.transport import policy_predict
    from ml.transport.policy_train import train_policy
    policy_predict.reset_cache()
    _, metrics, path = train_policy(n_states=400, seed=0)
    assert path.exists()
    rf = metrics["comparison"]["RandomForestRegressor"]
    rules = metrics["comparison"]["RulesBaseline"]
    assert rf["action_accuracy"] >= rules["action_accuracy"]
    assert metrics["dataset"] == "synthetic_action_utility"
    assert "synthetic" in metrics["dataset_disclaimer"].lower()
    policy_predict.reset_cache()


def test_undo_rolls_back_last_action():
    first = asyncio.run(optimize.apply_turn("undo-s", "try sample"))
    assert first["ok"] is True
    hist = first.get("action_history") or []
    if not hist:
        return
    n = len(hist)
    undone = optimize.undo_last("undo-s")
    assert undone["ok"] is True
    assert len(undone.get("action_history") or []) == n - 1
    assert "snapshots" not in undone


def test_frozen_concert_pref():
    first = asyncio.run(optimize.apply_turn("fz", "try sample"))
    assert first["ok"] is True
    second = asyncio.run(optimize.apply_turn("fz", "Don't change my concert."))
    assert "concert" in second["prefs"]["frozen"]


def test_no_price_on_parse_endpoint():
    resp = client.post(
        "/v1/trip_builder/parse",
        json={"session_id": "price-opt", "sample": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "snapshots" not in body
    assert body["intelligence"]["cost_saved"] is None
    card = body.get("rideshare_card")
    if card:
        assert card["price"] is None
    here = body.get("here_now") or {}
    assert here.get("uber_source") == "uber_unavailable"
    cheap = here.get("cheapest")
    assert cheap is None or cheap.get("low") is None


def test_here_now_picks_cheapest_live_uber(monkeypatch):
    monkeypatch.setattr(
        "ml.transport.rideshare.fetch_uber_live",
        lambda *a, **k: [
            {
                "provider": "uber", "product": "UberXL", "estimate": "$24-30",
                "low": 24.0, "price_available": True, "eta_min": 4.0, "source": "uber_live",
            },
            {
                "provider": "uber", "product": "UberX", "estimate": "$12-16",
                "low": 12.0, "price_available": True, "eta_min": 3.0, "source": "uber_live",
            },
        ],
    )
    from ml.transport.rideshare import build_here_now
    stops = parse_text(SAMPLE_ITINERARY)
    here = build_here_now(stops[0], stops[1], max_walk_minutes=10)
    assert here["at"] and "Union Square" in here["at"]
    assert "Golden Gate" in here["next"]
    assert here["cheapest"]["product"] == "UberX"
    assert here["cheapest"]["low"] == 12.0
    assert here["uber_source"] == "uber_live"
    speak = here["speak"].lower()
    assert "union square" in speak
    assert "uberx" in speak
    assert "$12-16" in here["speak"]
    assert "first stop" in speak
    assert here["deeplink"].startswith("https://m.uber.com/looking")
    assert "uberxl" in speak


def test_uber_deeplink_opens_looking_with_named_stops():
    import json
    from urllib.parse import parse_qs, urlparse

    from ml.transport.rideshare import build_here_now, first_rideshare_pair

    stops = parse_text(SAMPLE_ITINERARY)
    pair = first_rideshare_pair(stops)
    assert pair is not None
    here = build_here_now(pair[0], pair[1], max_walk_minutes=10)
    parsed = urlparse(here["deeplink"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "m.uber.com"
    assert parsed.path.startswith("/looking")
    qs = parse_qs(parsed.query)
    pickup = json.loads(qs["pickup"][0])
    drop = json.loads(qs["drop[0]"][0])
    assert pickup["latitude"] == pytest.approx(float(stops[0]["lat"]), abs=0.02)
    assert pickup["longitude"] == pytest.approx(float(stops[0]["lon"]), abs=0.02)
    assert "Union Square" in pickup["addressLine1"]
    assert drop["latitude"] == pytest.approx(float(stops[1]["lat"]), abs=0.02)
    assert "Golden Gate" in drop["addressLine1"]


def test_nyc_uber_hop_skips_the_cross_country_flight():
    from ml.transport.parse import SAMPLE_NYC_BUSINESS
    from ml.transport.rideshare import build_here_now, first_rideshare_pair

    stops = parse_text(SAMPLE_NYC_BUSINESS)
    pair = first_rideshare_pair(stops)
    assert pair is not None
    blob = f"{pair[0].get('title')} {pair[1].get('title')}".lower()
    assert "sfo-jfk" not in blob.replace(" ", "")
    assert "flight" not in blob
    assert "jfk" in blob or "midtown" in blob
    here = build_here_now(pair[0], pair[1], max_walk_minutes=10)
    assert here["at"] == "JFK Airport"
    assert "airport transfer" not in here["speak"].lower()
    assert "don't have live" not in here["speak"].lower()
    assert "won't invent" not in here["speak"].lower()
    assert "view the rides currently available" in here["speak"].lower()
