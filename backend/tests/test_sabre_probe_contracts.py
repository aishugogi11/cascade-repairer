"""Hermetic contracts for the CERT exploration probes (2026-07-14 replan).

The probes in specs/2026-07-13-sabre-cert-exploration/probes/ carry exit-code
guarantees the constitution now names (tech-stack.md § Testing): sweep.py
exits nonzero when any endpoint hits NETWORK-ERR, and booking_lifecycle.py
exits nonzero when createBooking drifts from the documented
UNAUTHORIZED_ACCESS entitlement wall. These tests load the probe scripts and
prove those guarantees with patched network calls — no credentials, no
network.

Like test_validator_docs_contract.py, the probe sources live outside the
backend image's build context, so this module skips inside the container and
runs from a full checkout.
"""
import io
import types
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES_DIR = REPO_ROOT / "specs" / "2026-07-13-sabre-cert-exploration" / "probes"

pytestmark = pytest.mark.skipif(
    not PROBES_DIR.exists(),
    reason="probe sources absent (running inside the backend image)",
)


def _load_probe(filename: str) -> types.ModuleType:
    path = PROBES_DIR / filename
    module = types.ModuleType(filename.removesuffix(".py"))
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


class _FakeHTTPSuccess:
    status = 200

    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.invalid", code, "err", None, io.BytesIO(b"{}")
    )


# --- sweep.py -------------------------------------------------------------


def test_sweep_network_error_exits_nonzero(monkeypatch):
    sweep = _load_probe("sweep.py")
    monkeypatch.setattr(sweep, "mint_token", lambda: "fake-token")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("severed")),
    )
    assert sweep.main() == 1


def test_sweep_all_endpoints_answering_exits_zero(monkeypatch):
    sweep = _load_probe("sweep.py")
    monkeypatch.setattr(sweep, "mint_token", lambda: "fake-token")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeHTTPSuccess())
    assert sweep.main() == 0


def test_sweep_classify_maps_http_codes_to_kinds(monkeypatch):
    sweep = _load_probe("sweep.py")
    expectations = {
        403: "NOT-ENTITLED",
        400: "SHAPE-400",
        404: "NOT-FOUND",
        500: "SERVER-ERR",
    }
    for code, kind in expectations.items():
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda *a, _code=code, **k: (_ for _ in ()).throw(_http_error(_code)),
        )
        assert sweep.classify("tok", f"probe-{code}", "GET", "/x") == kind


# --- booking_lifecycle.py ---------------------------------------------------


def _instaflights_payload() -> dict:
    depart = (date.today() + timedelta(days=30)).isoformat()
    return {
        "PricedItineraries": [
            {
                "AirItinerary": {
                    "OriginDestinationOptions": {
                        "OriginDestinationOption": [
                            {
                                "FlightSegment": [
                                    {
                                        "DepartureDateTime": f"{depart}T07:20:00",
                                        "FlightNumber": "439",
                                        "MarketingAirline": {"Code": "DL"},
                                        "DepartureAirport": {"LocationCode": "DFW"},
                                        "ArrivalAirport": {"LocationCode": "LAX"},
                                        "ResBookDesigCode": "E",
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        ]
    }


def _drive_lifecycle(monkeypatch, create_response: dict):
    """Run booking_lifecycle.main() with scripted network responses.

    Returns (exit_code, calls) where calls records (method, path, payload)."""
    lifecycle = _load_probe("booking_lifecycle.py")
    calls = []

    def fake_call(token, method, path, payload=None, timeout=180):
        calls.append((method, path, payload))
        if "/shop/flights" in path:
            return 200, _instaflights_payload()
        if path.endswith("createBooking"):
            return 200, create_response
        if path.endswith("cancelBooking"):
            return 200, {}
        raise AssertionError(f"unexpected probe call: {path}")

    monkeypatch.setattr(lifecycle, "mint_token", lambda: "fake-token")
    monkeypatch.setattr(lifecycle, "call", fake_call)
    return lifecycle.main(), calls


def test_lifecycle_documented_wall_exits_zero(monkeypatch):
    code, calls = _drive_lifecycle(
        monkeypatch,
        {
            "errors": [
                {
                    "category": "UNAUTHORIZED",
                    "type": "UNAUTHORIZED_ACCESS",
                    "description": "The service PassengerDetailsRQ returned an "
                    "authorization failure.",
                }
            ]
        },
    )
    assert code == 0
    assert not [c for c in calls if c[1].endswith("cancelBooking")]


def test_lifecycle_rejects_missing_unauthorized_access(monkeypatch):
    code, _ = _drive_lifecycle(
        monkeypatch,
        {"errors": [{"category": "APPLICATION_ERROR", "type": "OTHER"}]},
    )
    assert code == 1


def test_lifecycle_rejects_empty_errors_without_confirmation(monkeypatch):
    code, _ = _drive_lifecycle(monkeypatch, {"errors": []})
    assert code == 1


def test_lifecycle_unexpected_success_cancels_and_exits_nonzero(monkeypatch):
    code, calls = _drive_lifecycle(monkeypatch, {"confirmationId": "ZZZZZZ"})
    assert code == 1
    cancels = [c for c in calls if c[1].endswith("cancelBooking")]
    assert len(cancels) == 1
    assert cancels[0][2]["confirmationId"] == "ZZZZZZ"
