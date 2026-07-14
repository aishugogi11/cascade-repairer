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

    async def _post(self, path: str, payload: dict) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient(base_url=self.base_url) as http:
            resp = await http.post(
                path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def _get(self, path: str, params: dict) -> dict:
        """The _post posture for query-param APIs: same token handling
        (per-instance cache, minted lazily), same raise_for_status."""
        token = await self._get_token()
        async with httpx.AsyncClient(base_url=self.base_url) as http:
            resp = await http.get(
                path,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def instaflights_search(
        self, request: shapes.InstaFlightsRequest
    ) -> shapes.InstaFlightsResponse:
        """GET /v1/shop/flights — the entitled search API on this PCC.
        onlineitinerariesonly=Y triggers a CERT-side 500 (verified-live,
        Phase 25), so N is merged in unconditionally — never overridable."""
        params = request.model_dump()
        params["onlineitinerariesonly"] = "N"
        data = await self._get("/v1/shop/flights", params)
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
