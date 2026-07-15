"""Access-code gate — Phase 17.

A shared demo secret protecting real OpenAI / Vocal Bridge spend behind the
public Cloud Run URL: requests under /v1/ must carry the code in an
X-Access-Code header. A small allowlist stays public — the legal pages App
Store Connect must reach, POST /v1/auth/validate (the gate's own front
door), and the GET HTML page shells, which are inert without the gated JSON
APIs behind them.

Fail-open by design: with DEMO_ACCESS_CODE unset the gate allows everything
and warns once — local dev and the hermetic CI suite need zero setup. The
env var is read per request (the repo-wide pattern) so setting it on Cloud
Run via --update-env-vars — or monkeypatching it in tests — applies without
a redeploy. This is a demo gate, not a security boundary: the code ships in
App Review notes and the judges' hands; rotating it is an env-var update.
"""
import logging
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_PUBLIC_PREFIXES = ("/v1/legal/",)
_PUBLIC_POSTS = {"/v1/auth/validate"}
# The static HTML shells (with or without the trailing slash, so FastAPI's
# 307 redirect to the canonical path stays reachable too).
_PUBLIC_PAGES = {
    "/v1/web_call", "/v1/mobile_voice", "/v1/itinerary", "/v1/demo",
    "/v1/booking", "/v1/cascade",
}

_warned_open = False


def code_is_valid(presented: str) -> bool:
    """Constant-time check against DEMO_ACCESS_CODE; open when unset."""
    expected = os.environ.get("DEMO_ACCESS_CODE", "").strip()
    if not expected:
        return True
    return secrets.compare_digest(presented.strip(), expected)


def _is_public(method: str, path: str) -> bool:
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return True
    if method == "POST" and path in _PUBLIC_POSTS:
        return True
    return method == "GET" and path.rstrip("/") in _PUBLIC_PAGES


async def access_gate_middleware(request: Request, call_next):
    global _warned_open
    path = request.url.path
    if path.startswith("/v1/"):
        expected = os.environ.get("DEMO_ACCESS_CODE", "").strip()
        if not expected:
            if not _warned_open:
                _warned_open = True
                logger.warning(
                    "DEMO_ACCESS_CODE is not set — the /v1/ access gate is "
                    "open (expected for local dev and CI)."
                )
        elif not _is_public(request.method, path):
            presented = request.headers.get("X-Access-Code", "")
            if not secrets.compare_digest(presented.strip(), expected):
                return JSONResponse(
                    status_code=401,
                    content={"error": "missing or invalid access code"},
                )
    return await call_next(request)
