"""Real Sabre client — documented request construction, not called this phase.

Implements the same interface as MockSabreClient, building the HTTP requests
exactly as sabre-api-notes.md documents them. No sandbox credentials exist
this phase, so its correctness claim is "matches the notes file", not
"certified against CERT". Wiring and certifying it is event-day prep.

Configuration (all env vars):
- SABRE_BASE_URL   — e.g. https://api.cert.platform.sabre.com
- SABRE_CLIENT_SECRET — the pre-built Basic secret for POST /v2/auth/token
"""
import os
from typing import Optional

import httpx

from api.sabre import shapes


class SabreNotConfiguredError(RuntimeError):
    """Raised when real mode is invoked without Sabre credentials."""


# The documented InstaFlights "no results" answer (verified live 2026-07-14,
# re-probed 2026-07-14 for Phase 28): HTTP 404 whose JSON body carries
# errorCode WARN.RAF.APPLICATION and message "No results were found" — an
# empty result, not a failure. Strict match (Phase 28, decision 2): the
# error-code marker first, the message as fallback; any other 404 stays a
# genuine failure so the dispatcher's mock swap keeps covering real outages.
_NO_RESULTS_ERROR_CODE = "WARN.RAF.APPLICATION"
_NO_RESULTS_MESSAGE = "no results were found"


def _is_documented_no_results(response: httpx.Response) -> bool:
    """True only for the documented InstaFlights empty-cache 404 body."""
    if response.status_code != 404:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    if body.get("errorCode") == _NO_RESULTS_ERROR_CODE:
        return True
    return _NO_RESULTS_MESSAGE in str(body.get("message", "")).lower()


class RealSabreClient:
    """Same interface as MockSabreClient; constructs the documented calls."""

    def __init__(self):
        self.base_url = os.environ.get("SABRE_BASE_URL")
        self.client_secret = os.environ.get("SABRE_CLIENT_SECRET")
        self._token: Optional[str] = None
        # Lazy in-process cache (single Cloud Run instance, the standing
        # scope decision) — the supported-markets list changes on CERT's
        # timescale, not the demo's.
        self._markets: Optional[shapes.SupportedMarketsResponse] = None

    def _require_config(self) -> None:
        if not self.base_url or not self.client_secret:
            raise SabreNotConfiguredError(
                "Real Sabre mode needs SABRE_BASE_URL and SABRE_CLIENT_SECRET; "
                "neither is configured. Set SABRE_MODE=mock (the default) or "
                "provide sandbox credentials."
            )

    async def _get_token(self) -> str:
        """POST /v2/auth/token, client_credentials grant. Token lives ~7 days;
        we refetch per client instance and on 401 rather than trusting it."""
        self._require_config()
        if self._token is not None:
            return self._token
        async with httpx.AsyncClient(base_url=self.base_url) as http:
            resp = await http.post(
                "/v2/auth/token",
                headers={"Authorization": f"Basic {self.client_secret}"},
                data={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            token = shapes.TokenResponse.model_validate(resp.json())
        self._token = token.access_token
        return self._token

    async def _send_with_refresh(self, send) -> dict:
        """Send once with the cached token; on a 401 (the ~7-day expiry or a
        credential reset — _get_token's docstring promised this and Phase 28
        delivers it), clear the cache, mint a fresh token, and retry exactly
        once. A second 401 raises to the dispatcher's per-call mock swap —
        no retry loops on the voice turn path."""
        resp = await send(await self._get_token())
        if resp.status_code == 401:
            self._token = None
            resp = await send(await self._get_token())
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, payload: dict) -> dict:
        async def send(token: str) -> httpx.Response:
            async with httpx.AsyncClient(base_url=self.base_url) as http:
                return await http.post(
                    path,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

        return await self._send_with_refresh(send)

    async def _get(self, path: str, params: dict) -> dict:
        """The _post posture for query-param APIs: same token handling
        (per-instance cache, minted lazily, refreshed once on 401), same
        raise_for_status."""
        async def send(token: str) -> httpx.Response:
            async with httpx.AsyncClient(base_url=self.base_url) as http:
                return await http.get(
                    path,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )

        return await self._send_with_refresh(send)

    async def instaflights_search(
        self, request: shapes.InstaFlightsRequest
    ) -> shapes.InstaFlightsResponse:
        """GET /v1/shop/flights — the entitled search API on this PCC.
        onlineitinerariesonly=Y triggers a CERT-side 500 (verified-live,
        Phase 25), so N is merged in unconditionally — never overridable.

        InstaFlights signals an empty cache date as a documented 404
        (Phase 28): that one body becomes an empty response — the agent
        speaks the honest no-flights line instead of mock-swapped options.
        Every other status error re-raises to the dispatcher's insurance."""
        params = request.model_dump()
        params["onlineitinerariesonly"] = "N"
        try:
            data = await self._get("/v1/shop/flights", params)
        except httpx.HTTPStatusError as exc:
            if _is_documented_no_results(exc.response):
                return shapes.InstaFlightsResponse(PricedItineraries=[])
            raise
        return shapes.InstaFlightsResponse.model_validate(data)

    async def supported_markets(self) -> shapes.SupportedMarketsResponse:
        """GET /v1/lists/supported/shop/flights/origins-destinations —
        the city pairs InstaFlights carries, fetched lazily and cached on
        the instance. destinationcountry=US is the verified-live probe form
        (the demo's routes are domestic)."""
        if self._markets is None:
            data = await self._get(
                "/v1/lists/supported/shop/flights/origins-destinations",
                {"destinationcountry": "US"},
            )
            self._markets = shapes.SupportedMarketsResponse.model_validate(data)
        return self._markets

    async def flight_search(
        self, request: shapes.FlightSearchRequest
    ) -> shapes.FlightSearchResponse:
        data = await self._post(
            "/v5/offers/shop", request.model_dump(exclude_none=True)
        )
        return shapes.FlightSearchResponse.model_validate(data)

    async def create_booking(
        self, request: shapes.CreateBookingRequest
    ) -> shapes.CreateBookingResponse:
        data = await self._post(
            "/v1/trip/orders/createBooking", request.model_dump(exclude_none=True)
        )
        return shapes.CreateBookingResponse.model_validate(data)

    async def cancel_booking(
        self, request: shapes.CancelBookingRequest
    ) -> shapes.CancelBookingResponse:
        data = await self._post(
            "/v1/trip/orders/cancelBooking", request.model_dump(exclude_none=True)
        )
        return shapes.CancelBookingResponse.model_validate(data)

    async def rebook_flight(
        self, request: shapes.RebookFlightRequest
    ) -> shapes.RebookFlightResponse:
        """No single REST endpoint: cancel the old flight items, then book the
        replacement (the documented unticketed-PNR path)."""
        cancelled = await self.cancel_booking(request.cancel)
        created = await self.create_booking(request.create)
        return shapes.RebookFlightResponse(cancelled=cancelled, created=created)

    async def modify_booking(
        self, request: shapes.ModifyBookingRequest
    ) -> shapes.ModifyBookingResponse:
        data = await self._post(
            "/v1/trip/orders/modifyBooking", request.model_dump(exclude_none=True)
        )
        return shapes.ModifyBookingResponse.model_validate(data)
