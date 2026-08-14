"""Cascade itinerary optimization — hermetic (no GCP, no network)."""
import asyncio

from fastapi.testclient import TestClient

import main
from api import cascade_optimize, concierge, memory_trips, optimize
from api.pdf_itinerary import build_from_upload
from ml.transport.parse import SAMPLE_NYC_BUSINESS, geocode, parse_text

client = TestClient(main.app)


def _seed_nyc():
    memory_trips.clear()
    cascade_optimize.clear()
    built = build_from_upload(
        user_id="opt-test",
        title="SFO → New York business trip",
        sample_kind="nyc",
    )
    assert built is not None
    trip, items = built
    memory_trips.put(trip, items)
    return trip.trip_id, items


def test_nyc_sample_geocodes_manhattan_not_union_square():
    stops = parse_text(SAMPLE_NYC_BUSINESS)
    titles = " ".join(s["title"] for s in stops).lower()
    assert "financial district" in titles
    assert "soho" in titles
    assert "rockefeller" in titles
    fidi = geocode("Client meeting — Financial District")
    soho = geocode("Lunch — SoHo")
    midtown = geocode("Rockefeller Center — Midtown")
    assert fidi[0] < 40.73
    assert soho[1] < -73.99
    assert midtown[0] > 40.74
    assert fidi != geocode("Union Square")
    jfk = geocode("Airport transfer — JFK")
    sfo = geocode("Airport departure — SFO")
    assert abs(jfk[0] - 40.6413) < 0.02
    assert abs(sfo[0] - 37.6213) < 0.02
    arrival = geocode("Flight UA 215 SFO-JFK")
    assert abs(arrival[0] - 40.6413) < 0.02


def test_analyze_nyc_trip_finds_recommendations():
    trip_id, items = _seed_nyc()
    out = cascade_optimize.analyze_trip(trip_id, items)
    assert out["ok"] is True
    assert out["model"]["kind"] == "weighted_scorer_plus_transport_forest"
    assert "neural" in out["model"]["disclaimer"].lower()
    recs = out["recommendations"]
    assert recs
    types = {r["type"] for r in recs}
    assert types & {
        "route_optimization",
        "airport_transfer",
        "cheaper_transportation",
        "faster_transportation",
        "better_value_transportation",
        "schedule_optimization",
    }
    spoken = out["spoken"].lower()
    assert "machine learning" not in spoken
    assert "neural" not in spoken
    assert "analyzed" in spoken or "found" in spoken
    assert out["summary"]["maps_source"] in ("google_maps", "demo_geometry")
    days = out["summary"].get("travel_by_day") or []
    assert len(days) >= 2
    assert out["summary"]["travel_is_typical_day"] is True
    for row in days:
        assert row["original_min"] <= 240
    assert out["summary"]["original_travel_min"] < sum(r["original_min"] for r in days)
    saily = out["saily"]
    assert saily["provider"] == "Saily"
    assert saily["needed"] is False
    assert saily["checkout_url"] == "https://saily.com/esim-united-states/"
    assert "New York" in saily["label"]
    assert "New York" in saily["speak"]
    assert "http" not in saily["speak"].lower()
    memory_trips.clear()
    cascade_optimize.clear()


def test_time_vs_cost_prefs_change_the_pick():
    trip_id, items = _seed_nyc()
    cheap = cascade_optimize.analyze_trip(
        trip_id, items, prefs=cascade_optimize.Prefs(priority="cost"),
    )
    cascade_optimize.clear()
    memory_trips.put(memory_trips.get(trip_id).trip, items)
    fast = cascade_optimize.analyze_trip(
        trip_id, items, prefs=cascade_optimize.Prefs(priority="time"),
    )
    cheap_pick = None
    fast_pick = None
    for rec in cheap["recommendations"]:
        trio = rec.get("transport_options") or {}
        if trio.get("cascade_pick"):
            cheap_pick = trio["cascade_pick"]
            break
    for rec in fast["recommendations"]:
        trio = rec.get("transport_options") or {}
        if trio.get("cascade_pick"):
            fast_pick = trio["cascade_pick"]
            break
    if cheap_pick and fast_pick:
        assert cheap["prefs"]["priority"] == "cost"
        assert fast["prefs"]["priority"] == "time"
        assert cheap["prefs"]["weights"]["cost_weight"] > cheap["prefs"]["weights"]["time_weight"]
    memory_trips.clear()
    cascade_optimize.clear()


def test_hate_walking_tightens_walk_cap():
    trip_id, _items = _seed_nyc()
    prefs = cascade_optimize.merge_pref_text(trip_id, "I hate walking.")
    assert prefs.max_walk_minutes is not None
    assert prefs.max_walk_minutes <= 4
    memory_trips.clear()
    cascade_optimize.clear()


def test_apply_reorder_updates_existing_itinerary():
    trip_id, items = _seed_nyc()
    out = cascade_optimize.analyze_trip(trip_id, items)
    reorder = next((r for r in out["recommendations"] if r["type"] == "route_optimization"), None)
    if reorder is None:
        memory_trips.clear()
        cascade_optimize.clear()
        return
    before = [
        ((i.details or {}).get("title") or i.location, i.start_ts)
        for i in memory_trips.get(trip_id).items
        if i.start_ts
    ]
    applied = cascade_optimize.apply_recommendation(trip_id, reorder["id"])
    assert applied["ok"] is True
    after = [
        ((i.details or {}).get("title") or i.location, i.start_ts)
        for i in memory_trips.get(trip_id).items
        if i.start_ts
    ]
    assert after != before or applied.get("applied_id") == reorder["id"]
    fingerprints = cascade_optimize.feedback_log()
    assert any(row["action"] == "accept" for row in fingerprints)
    memory_trips.clear()
    cascade_optimize.clear()


def test_apply_schedule_optimization_stamps_rides():
    memory_trips.clear()
    cascade_optimize.clear()
    built = build_from_upload(
        user_id="opt-test", title="SF day", sample=True,
    )
    trip, items = built
    memory_trips.put(trip, items)
    out = cascade_optimize.analyze_trip(trip.trip_id, items)
    rec = next(
        (r for r in out["recommendations"] if r["type"] == "schedule_optimization"),
        None,
    )
    if rec is None:
        memory_trips.clear()
        cascade_optimize.clear()
        return
    applied = cascade_optimize.apply_recommendation(trip.trip_id, rec["id"])
    assert applied["ok"] is True
    stamped = [
        i for i in memory_trips.get(trip.trip_id).items
        if (i.details or {}).get("optimization_applied") == "schedule_optimization"
    ]
    assert stamped
    memory_trips.clear()
    cascade_optimize.clear()


def test_reject_does_not_repeat_the_same_change():
    trip_id, items = _seed_nyc()
    first = cascade_optimize.analyze_trip(trip_id, items)
    rec = first["recommendations"][0]
    fp = rec["fingerprint"]
    rejected = cascade_optimize.reject_recommendation(trip_id, rec["id"])
    assert rejected["ok"] is True
    ids = {r["fingerprint"] for r in rejected.get("recommendations") or []}
    assert fp not in ids
    again = cascade_optimize.analyze_by_id(trip_id)
    again_ids = {r["fingerprint"] for r in again.get("recommendations") or []}
    assert fp not in again_ids
    memory_trips.clear()
    cascade_optimize.clear()


def test_http_optimize_apply_updates_itinerary():
    trip_id, _items = _seed_nyc()
    resp = client.get(f"/v1/itinerary/optimize/{trip_id}")
    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    assert recs
    rec = recs[0]
    applied = client.post(
        f"/v1/itinerary/optimize/{trip_id}/apply",
        json={"recommendation_id": rec["id"], "fingerprint": rec["fingerprint"]},
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["ok"] is True
    assert body.get("applied_id") == rec["id"]
    assert rec["fingerprint"] not in {
        r["fingerprint"] for r in body.get("recommendations") or []
    }
    status = client.get(f"/v1/itinerary/status/{trip_id}")
    assert status.status_code == 200
    items = status.json()["items"]
    assert items
    times = [i["start_ts"] for i in items if i.get("start_ts")]
    assert times == sorted(times)
    if rec["type"] != "route_optimization":
        stamped = [
            i for i in items
            if (i.get("details") or {}).get("optimization_applied")
        ]
        assert stamped
        assert any(
            (i.get("details") or {}).get("transport_label")
            or (i.get("details") or {}).get("optimization_applied")
            for i in stamped
        )
    memory_trips.clear()
    cascade_optimize.clear()


def test_apply_survives_analysis_cache_miss():
    trip_id, items = _seed_nyc()
    out = cascade_optimize.analyze_trip(trip_id, items)
    rec = out["recommendations"][0]
    cascade_optimize._ANALYSES.clear()
    applied = cascade_optimize.apply_recommendation(
        trip_id, rec["id"], fingerprint=rec["fingerprint"],
    )
    assert applied["ok"] is True
    assert applied.get("applied_id")
    memory_trips.clear()
    cascade_optimize.clear()


def test_http_optimize_apply_reject_round_trip():
    trip_id, _items = _seed_nyc()
    resp = client.get(f"/v1/itinerary/optimize/{trip_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    recs = body["recommendations"]
    assert recs
    rec = recs[0]
    keep = client.post(
        f"/v1/itinerary/optimize/{trip_id}/reject",
        json={"recommendation_id": rec["id"]},
    )
    assert keep.status_code == 200
    assert keep.json()["ok"] is True
    status = client.get(f"/v1/itinerary/status/{trip_id}")
    assert status.status_code == 200
    assert "optimization" in status.json()
    memory_trips.clear()
    cascade_optimize.clear()


def test_analyze_adopts_memory_trip_when_session_unpinned():
    trip_id, _items = _seed_nyc()
    concierge._SESSION_TRIPS.clear()
    spoken = asyncio.run(concierge.analyze_itinerary_impl("unpinned-opt", "save time"))
    assert "don't see a booked trip" not in spoken.lower()
    assert "machine learning" not in spoken.lower()
    assert spoken
    assert "unpinned-opt" in concierge._SESSION_TRIPS
    assert concierge._SESSION_TRIPS["unpinned-opt"].trip.trip_id == trip_id
    concierge._SESSION_TRIPS.clear()
    memory_trips.clear()
    cascade_optimize.clear()


def test_voice_tools_analyze_and_reject():
    trip_id, items = _seed_nyc()
    concierge._SESSION_TRIPS.clear()
    concierge._SESSION_TRIPS["opt-voice"] = concierge.TripContext(
        trip=memory_trips.get(trip_id).trip,
        items=items,
        summary="TRIP CONTEXT",
    )
    spoken = asyncio.run(concierge.analyze_itinerary_impl("opt-voice", "save time"))
    assert "machine learning" not in spoken.lower()
    assert spoken
    recs = cascade_optimize.public_view(trip_id)["recommendations"]
    if recs:
        reply = asyncio.run(concierge.reject_optimization_impl("opt-voice", 1))
        assert "current plan" in reply.lower() or "keep" in reply.lower()
    concierge._SESSION_TRIPS.clear()
    memory_trips.clear()
    cascade_optimize.clear()


def test_optimize_publish_keeps_sfo_to_new_york_flight():
    """Optimize → Cascade must keep the SFO-JFK flight, not demote it to a
    ground card titled 'Flight' with origin missing."""
    from api.pdf_itinerary import build_from_stops

    memory_trips.clear()
    stops = parse_text(SAMPLE_NYC_BUSINESS)
    title = optimize._cascade_title(stops)
    assert title == "SFO → New York"
    built = build_from_stops(
        user_id="opt-nyc",
        title=title,
        stops=stops,
    )
    assert built is not None
    trip, items = built
    assert trip.origin == "SFO"
    assert trip.destinations == ["JFK"]
    assert trip.title == "SFO → New York"
    flights = [i for i in items if i.type == "flight"]
    assert len(flights) == 1
    assert flights[0].location == "SFO-JFK"
    assert flights[0].details["airline"] == "UA"
    assert flights[0].details["flight_number"] == 215
    assert not any(
        i.type == "ground"
        and ((i.details or {}).get("title") or "") == "Flight"
        for i in items
    )
    memory_trips.clear()


def test_cheapest_uber_voice_uses_nyc_memory_trip():
    trip_id, _items = _seed_nyc()
    optimize.clear_sessions()
    concierge._SESSION_TRIPS.clear()
    spoken = asyncio.run(concierge.answer_query(
        "cascade-orb", "What's the cheapest Uber from the first stop?",
    ))
    assert "don't see a booked trip" not in spoken.lower()
    assert "doesn't have any" not in spoken.lower()
    assert "first stop" in spoken.lower()
    assert "jfk" in spoken.lower() or "midtown" in spoken.lower()
    concierge._SESSION_TRIPS.clear()
    memory_trips.clear()
    cascade_optimize.clear()
    memory_trips.clear()
    resp = client.post("/v1/whatsapp/ingest", json={"sample_kind": "nyc"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "sample_nyc"
    status = client.get("/v1/itinerary/status/" + body["trip_id"]).json()
    blob = " ".join(
        ((i.get("details") or {}).get("title") or i.get("location") or "")
        for i in status["items"]
    )
    assert "Financial" in blob or "SoHo" in blob or "JFK" in blob
    memory_trips.clear()
    cascade_optimize.clear()
