"""Cascade dashboard — Phase 22, the repair-beat surface.

Serves the consolidated demo page shell only; everything it displays is
driven by the JSON endpoints the other surfaces already expose
(/v1/itinerary status + trips, /v1/sabre_tools/latest_trip_id), and its
trigger controls call the existing /v1/demo orchestrator. The booking_ui
thin-router shape: no logic here, and the HTML is read per request because
uvicorn --reload only watches .py files.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

cascade_ui = APIRouter()

_PAGE_PATH = Path(__file__).parent / "assets" / "cascade" / "page.html"


@cascade_ui.get("/", response_class=HTMLResponse)
def cascade_page():
    return _PAGE_PATH.read_text()
