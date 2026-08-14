"""Delay-risk model + preference ranking — hermetic (no GCP, no network)."""
import asyncio

from fastapi.testclient import TestClient

import main
from api import concierge
from api.flight_options import FlightOption
from ml.data import generate_delay_dataset
from ml.evaluate import evaluate
from ml.features import FEATURE_COLUMNS, features_from_option
from ml.model import build_model
from ml.ranking import TravelerPrefs, parse_clock, rank_options
from ml.train import train


def _opt(**kwargs):
    defaults = dict(
        option_number=1, airline="AA", flight_number=100, origin="JFK",
        destination="LAX", depart_date="2026-08-01", depart_time="08:00",
        arrive_time="10:05", stops=0, price=200.0, currency="USD",
        spoken="Option one.", airline_name="American", duration_minutes=125,
    )
    defaults.update(kwargs)
    return FlightOption(**defaults)


def test_parse_clock_variants():
    assert parse_clock("9 AM") == "09:00"
    assert parse_clock("9") == "09:00"
    assert parse_clock("13:30") == "13:30"
    assert parse_clock("not a time") is None


def test_features_from_option_degrades_missing_duration():
    row = features_from_option(_opt(duration_minutes=0, stops=1))
    assert row["stops"] == 1
    assert row["is_connection"] == 1
    assert row["duration_minutes"] > 0


def test_train_tiny_model_beats_chance(tmp_path, monkeypatch):
    """A few thousand BTS-calibrated rows are enough for ROC-AUC > 0.7."""
    monkeypatch.setattr("ml.model.MODEL_PATH", tmp_path / "delay_risk.joblib")
    monkeypatch.setattr("ml.model.METRICS_PATH", tmp_path / "metrics.json")
    _, metrics, path = train(n=4000, seed=0)
    assert metrics["roc_auc"] >= 0.70
    assert metrics["n_test"] == 800
    assert path.exists()
    assert set(FEATURE_COLUMNS) <= set(metrics["features"])


def test_in_process_fit_has_all_classification_metrics():
    frame = generate_delay_dataset(n=800, seed=1)
    X, y = frame[FEATURE_COLUMNS], frame["delayed_15"]
    pipe = build_model()
    pipe.fit(X, y)
    metrics = evaluate(pipe, X, y)
    for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
        assert 0.0 <= metrics[key] <= 1.0


def test_risk_priority_puts_safer_flight_first(monkeypatch):
    risks = {"AA": 0.12, "UA": 0.41}

    def fake_predict(option):
        r = risks[option.airline]
        return {"delay_risk": r, "delay_risk_pct": int(r * 100),
                "factors": [], "source": "test"}

    monkeypatch.setattr("ml.ranking.predict_delay_risk", fake_predict)
    cheap_risky = _opt(option_number=1, airline="UA", airline_name="United",
                       price=130, stops=1, arrive_time="09:00")
    dear_safe = _opt(option_number=2, airline="AA", price=180, stops=0,
                     arrive_time="09:00")
    ranked = rank_options([cheap_risky, dear_safe], TravelerPrefs(priority="risk"))
    assert ranked[0].option.airline == "AA"
    assert ranked[0].recommended is True
    assert any("cheaper" in w.lower() for w in ranked[0].why)


def test_price_priority_puts_cheapest_first(monkeypatch):
    monkeypatch.setattr(
        "ml.ranking.predict_delay_risk",
        lambda o: {"delay_risk": 0.2, "delay_risk_pct": 20,
                   "factors": [], "source": "test"},
    )
    ranked = rank_options(
        [_opt(airline="AA", price=180), _opt(airline="UA", price=130, stops=1)],
        TravelerPrefs(priority="price"),
    )
    assert ranked[0].option.airline == "UA"


def test_arrive_before_window_penalizes_late_flights(monkeypatch):
    monkeypatch.setattr(
        "ml.ranking.predict_delay_risk",
        lambda o: {"delay_risk": 0.15, "delay_risk_pct": 15,
                   "factors": [], "source": "test"},
    )
    early = _opt(airline="B6", airline_name="JetBlue", arrive_time="08:50",
                 price=198)
    late = _opt(airline="AA", arrive_time="10:05", price=187.6)
    ranked = rank_options(
        [late, early],
        TravelerPrefs(priority="arrival", arrive_before="09:00"),
    )
    assert ranked[0].option.airline == "B6"
    assert ranked[1].misses_arrival_window is True


def test_set_recovery_preferences_reranks_without_searching(monkeypatch):
    monkeypatch.setattr(
        "ml.ranking.predict_delay_risk",
        lambda o: {
            "delay_risk": 0.4 if o.stops else 0.12,
            "delay_risk_pct": 40 if o.stops else 12,
            "factors": [], "source": "test",
        },
    )
    session = "ml-rerank"
    concierge._SESSION_PREFS.pop(session, None)
    concierge._SESSION_FLIGHT_OPTIONS.pop(session, None)
    try:
        asyncio.run(concierge.search_flights_impl(
            session, "JFK", "LAX", "2026-08-01"
        ))
        first = concierge._SESSION_FLIGHT_OPTIONS[session][0]
        spoken = asyncio.run(concierge.set_recovery_preferences_impl(
            session, priority="price",
        ))
        reranked = concierge._SESSION_FLIGHT_OPTIONS[session]
        assert reranked[0].price == min(o.price for o in reranked)
        assert "I recommend option one" in spoken
        assert concierge._prefs_for(session).priority == "price"
        # Rerank used the stored set — a new search would replace the slot
        # timestamp; prefs are what changed.
        assert first.airline in {o.airline for o in reranked}
        dates = concierge._LATEST_SEARCH.available_dates
        assert len(dates) == 7
        assert dates[0]["selected"] is True
    finally:
        concierge._SESSION_FLIGHT_OPTIONS.pop(session, None)
        concierge._SESSION_PREFS.pop(session, None)
        concierge._LATEST_SEARCH = None


def test_metrics_endpoint_reports_source():
    client = TestClient(main.app)
    resp = client.get("/v1/ml/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] in ("trained_artifact", "heuristic_fallback")
    assert "artifact" in body
