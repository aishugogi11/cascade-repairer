"""Sabre dispatcher — picks mock vs real per call from SABRE_MODE.

SABRE_MODE (`mock` | `real`, default `mock`) is read at call time, not import
time: tests flip it with monkeypatch.setenv, and Cloud Run flips it with an
`--update-env-vars` merge — no rebuild, no code change.

In `real` mode any failure (missing config, HTTP error, shape mismatch)
falls back to the mock **for that call** and logs a warning naming the
operation and error — event-day insurance if the sandbox flakes during
judging. The judges see the cascade either way.
"""
import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, List, Optional, Set, Tuple

from api.sabre import shapes
from api.sabre.mock_client import MockSabreClient
from api.sabre.real_client import RealSabreClient

logger = logging.getLogger(__name__)

_mock = MockSabreClient()
_real = RealSabreClient()

# --- live-search log (Phase 23) — the dashboard's search panel feed ------------
# A bounded in-process ring of the most recent *search* operations (shopping
# only — booking ops are writes, not searches), recorded at the dispatch
# boundary so it reflects what actually ran: real, mock, or a real-mode
# fallback. Best-effort by contract — recording can never break a search.

_SEARCH_OPS = {"flight_search", "instaflights_search"}
_SEARCH_LOG: deque = deque(maxlen=25)


def _search_route(request: Any) -> Tuple[Optional[str], Optional[str]]:
    """(route, date) summaries, best-effort across the two search request
    shapes: InstaFlights carries flat origin/destination/departuredate; BFM
    nests them under OTA_AirLowFareSearchRQ.OriginDestinationInformation."""
    origin = getattr(request, "origin", None)
    destination = getattr(request, "destination", None)
    depart = getattr(request, "departuredate", None)
    if origin and destination:
        return f"{origin} → {destination}", depart
    try:
        legs = request.OTA_AirLowFareSearchRQ.OriginDestinationInformation
        first = legs[0]
        return (
            f"{first.OriginLocation.LocationCode} → "
            f"{first.DestinationLocation.LocationCode}",
            getattr(first, "DepartureDateTime", None),
        )
    except Exception:  # noqa: BLE001 — summary only, never load-bearing
        return None, None


def _search_outcome(response: Any) -> str:
    """A short outcome label from either search response shape — the
    itinerary count when it's readable, 'ok' when it isn't."""
    try:
        if isinstance(response, shapes.InstaFlightsResponse):
            count = len(response.PricedItineraries)
        else:
            count = response.groupedItineraryResponse.statistics.itineraryCount
    except Exception:  # noqa: BLE001
        return "ok"
    return "no fares" if count == 0 else f"{count} fares"


def _note_search(operation: str, request: Any, mode: str, response: Any) -> None:
    """Record one search into the ring — newest first. Any failure logs at
    debug and drops the entry; the search result is already on its way."""
    if operation not in _SEARCH_OPS:
        return
    try:
        route, depart = _search_route(request)
        _SEARCH_LOG.appendleft({
            "at": datetime.now(timezone.utc).isoformat(),
            "op": operation,
            "mode": mode,
            "route": route,
            "date": depart,
            "outcome": _search_outcome(response),
        })
    except Exception:  # noqa: BLE001 — never load-bearing
        logger.debug("search-log recording failed", exc_info=True)


def search_log() -> List[dict]:
    """The recent searches, newest first — the /v1/sabre_tools/search_log
    payload."""
    return list(_SEARCH_LOG)


def sabre_mode() -> str:
    """The runtime flag, read per call. Anything but 'real' means mock."""
    return os.environ.get("SABRE_MODE", "mock").strip().lower()


async def _dispatch(operation: str, request: Any) -> Any:
    mode = "mock"
    if sabre_mode() == "real":
        try:
            response = await getattr(_real, operation)(request)
            _note_search(operation, request, "real", response)
            return response
        except Exception as exc:  # noqa: BLE001 — any real-mode failure falls back
            logger.warning(
                "Sabre real-mode call %s failed (%s: %s) — falling back to "
                "the mock for this call",
                operation, type(exc).__name__, exc,
            )
            mode = "fallback"
    response = await getattr(_mock, operation)(request)
    _note_search(operation, request, mode, response)
    return response


async def flight_search(
    request: shapes.FlightSearchRequest,
) -> shapes.FlightSearchResponse:
    return await _dispatch("flight_search", request)


async def instaflights_search(
    request: shapes.InstaFlightsRequest,
) -> shapes.InstaFlightsResponse:
    return await _dispatch("instaflights_search", request)


async def supported_markets() -> Optional[Set[Tuple[str, str]]]:
    """The city pairs InstaFlights carries, as (origin, destination) — a
    best-effort helper, not a _dispatch operation: None in mock mode and on
    any failure, and callers skip market validation on None (requirements,
    decision 4). Never falls back to a mock list — an invented market list
    would turn the honest speakable redirect into a wrong answer."""
    if sabre_mode() != "real":
        return None
    try:
        response = await _real.supported_markets()
        pairs = {
            (
                pair.OriginLocation.AirportCode.upper(),
                pair.DestinationLocation.AirportCode.upper(),
            )
            for pair in response.OriginDestinationLocations
        }
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            "Sabre supported-markets fetch failed (%s: %s) — skipping "
            "market validation for this call",
            type(exc).__name__, exc,
        )
        return None
    # An empty list can't be a real market map — treat it as no answer
    # rather than redirecting every route.
    return pairs or None


async def create_booking(
    request: shapes.CreateBookingRequest,
) -> shapes.CreateBookingResponse:
    return await _dispatch("create_booking", request)


async def cancel_booking(
    request: shapes.CancelBookingRequest,
) -> shapes.CancelBookingResponse:
    return await _dispatch("cancel_booking", request)


async def rebook_flight(
    request: shapes.RebookFlightRequest,
) -> shapes.RebookFlightResponse:
    return await _dispatch("rebook_flight", request)


async def modify_booking(
    request: shapes.ModifyBookingRequest,
) -> shapes.ModifyBookingResponse:
    return await _dispatch("modify_booking", request)
