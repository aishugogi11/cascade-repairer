"""Legal pages for the App Store submission — Phase 16.

App Store Connect requires a privacy policy URL and a support URL; these
routes serve both as self-contained static HTML from assets/legal/, giving
them stable Cloud Run URLs versioned in-repo with no new infra. Files are
read per request (the /v1/itinerary pattern): uvicorn --reload only watches
.py files, so an import-time read would serve stale HTML all through local
dev.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

legal = APIRouter()

_ASSETS = Path(__file__).parent / "assets" / "legal"


@legal.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return (_ASSETS / "privacy.html").read_text()


@legal.get("/support", response_class=HTMLResponse)
def support_page():
    return (_ASSETS / "support.html").read_text()
