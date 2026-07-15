"""Phase 23 integration test — the whole consent-gated contract, one loop.

break → Call 1 (consent ask) → transcript read → yes → repairs launch and
land → Call 2 speaks the actual results. Everything external is mocked at
the established seams (vb_cli, the repositories, the classifier); the
consent registry, the watcher, and the purpose builders run for real. The
disrupt handler is driven directly inside one asyncio loop so the spawned
watcher task can be awaited to completion — hermetic, no network, no
OPENAI_API_KEY, no quota.
"""
import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from api import consent
from api import demo as demo_module
from api.repositories.models import ItineraryItem, Trip

_PACIFIC = ZoneInfo("America/Los_Angeles")

TRANSCRIPT = (
    "AGENT: Your flight from New York to Los Angeles was cancelled. I can "
    "rebook it and recheck the rest of the trip — want me to?\n\n"
    "USER: Yeah."
)


def test_full_consent_gated_flow_break_to_results_call(monkeypatch):
    consent.reset()
    for name, value in (
        ("VOCAL_BRIDGE_API_KEY", "k"),
        ("VOCAL_BRIDGE_CALLER_AGENT_ID", "a"),
        ("VOCAL_BRIDGE_CALLEE_PHONE", "+15555550123"),
    ):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(demo_module, "_CONSENT_POLL_SECONDS", 0.001)
    monkeypatch.setattr(demo_module, "_CONSENT_TIMEOUT_SECONDS", 1.0)

    trip = Trip(
        trip_id="t-int", user_id="demo-traveler", title="Trip to LAX",
        status="booked", origin="JFK", destinations=["LAX"],
        start_date=date(2026, 7, 17), end_date=date(2026, 7, 19),
    )
    items = [
        ItineraryItem(
            item_id="i-flight", trip_id="t-int", type="flight",
            status="booked", location="JFK-LAX",
            start_ts=datetime(2026, 7, 17, 8, 0, tzinfo=_PACIFIC),
        ),
        ItineraryItem(item_id="i-hotel", trip_id="t-int", type="hotel",
                      status="booked"),
        ItineraryItem(item_id="i-ground", trip_id="t-int", type="ground",
                      status="booked"),
    ]

    calls = []

    def fake_place_call(purpose, name=None):
        calls.append((name, purpose))
        return True, {"call_id": f"c-{len(calls)}", "status": "initiated"}, None

    monkeypatch.setattr(demo_module.vb_cli, "place_call", fake_place_call)
    monkeypatch.setattr(
        demo_module.vb_cli, "find_session",
        lambda call_id, lookback=50: (True, {
            "id": call_id, "call_status": "completed",
            "transcript_text": TRANSCRIPT,
        }, None),
    )

    async def fake_classify(transcript):
        assert "Yeah" in transcript
        return "yes"

    monkeypatch.setattr(demo_module.consent, "classify_consent", fake_classify)

    monkeypatch.setattr(
        demo_module.trips, "get_trip", lambda tid: (True, trip, None)
    )
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip",
        lambda tid: (True, items, None),
    )

    def fake_break(trip_id):
        items[0].status = "broken"
        return {"trip_id": trip_id, "item_id": "i-flight",
                "previous_status": "booked", "status": "broken",
                "affected_rows": 1}

    monkeypatch.setattr(demo_module, "break_trip_flight", fake_break)

    launched = []

    def fake_launch(session_id, launch_items):
        async def repair():
            await asyncio.sleep(0.005)
            for item in items:
                item.status = "fixed"

        launched.append(session_id)
        return ["rebook_flight"], [asyncio.create_task(repair())]

    monkeypatch.setattr(demo_module, "launch_trip_repairs", fake_launch)

    async def fake_details(tid, its):
        return {
            "i-flight": {
                "why_chosen": "Rebooked on Delta 1445, nonstop, landing "
                              "11:30 AM — the closest available arrival.",
                "price_delta": "+$23",
                "impact": "Every downstream booking was re-checked.",
            }
        }

    monkeypatch.setattr(demo_module, "_details_for", fake_details)

    async def scenario():
        response = await demo_module.disrupt(
            demo_module.DisruptRequest(trip_id="t-int")
        )
        # The click did two things only: the flight is broken, the wait is
        # registered, and nothing has launched yet.
        assert response["consent"] == consent.AWAITING
        assert items[0].status == "broken"
        assert launched == []
        assert consent.current("t-int").state == consent.AWAITING
        # Let the spawned watcher run the rest of the contract.
        await asyncio.gather(*list(demo_module._WATCHER_TASKS))
        return response

    response = asyncio.run(scenario())

    # Consent granted; repairs launched under a fresh demo session.
    assert consent.current("t-int").state == consent.GRANTED
    assert len(launched) == 1 and launched[0].startswith("demo-")
    assert items[0].status == "fixed"

    # Two calls, in order: the consent ask, then the results callback —
    # both speaking the real trip, the second speaking the real repair.
    assert [name for name, _ in calls] == [
        "demo-beat2-disruption", "demo-beat3-results",
    ]
    ask = calls[0][1]
    assert "New York" in ask and "Los Angeles" in ask
    assert "want me to?" in ask
    results = calls[1][1]
    assert "Delta 1445" in results
    assert "$23 more" in results
    assert "re-checked" in results
    assert "Minneapolis" not in ask and "Minneapolis" not in results
    # No purpose ever carries the callee number or the API key.
    for purpose in (ask, results):
        assert "+15555550123" not in purpose
        assert "VOCAL_BRIDGE" not in purpose
    assert response["call_id"] == "c-1"
