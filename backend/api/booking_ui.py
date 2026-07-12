"""Voice booking page — Phase 21, the pre-disruption beat's surface.

Serves the booking page shell only; everything on it is driven by the JSON
endpoints the other surfaces already expose (/v1/itinerary status + trips,
/v1/sabre_tools/latest_trip_id). The itinerary_ui thin-router shape: no
logic here, and the HTML is read per request because uvicorn --reload only
watches .py files.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

booking_ui = APIRouter()

_PAGE_PATH = Path(__file__).parent / "assets" / "booking" / "page.html"


@booking_ui.get("/", response_class=HTMLResponse)
def booking_page():
    return _PAGE_PATH.read_text()
