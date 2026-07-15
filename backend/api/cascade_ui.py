"""Cascade dashboard — Phase 22's repair-beat surface, carrying Phase 23's
live voice column.

Serves the consolidated demo page shell; everything it displays is driven
by the JSON endpoints the other surfaces already expose (/v1/itinerary
status + trips, /v1/sabre_tools/latest_trip_id + search_log), its trigger
controls call the existing /v1/demo orchestrator, and its center-column
voice orb rides the /v1/web_call wiring (server-minted token, useAIAgent →
/query). The booking_ui thin-router shape: no logic here, and the HTML is
read per request because uvicorn --reload only watches .py files.

The one templating step: the pinned VB CDN versions are injected from
web_call.py at serve time (the mobile_voice no-drift rule — the orb must
run the exact SDK versions the web_call surface runs, never a copy-pasted
literal). safe_substitute, because the page's own JS template literals
(`${...}`) must pass through untouched.
"""
from pathlib import Path
from string import Template

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.web_call import REACT_VER, VB_REACT_VER, VB_SDK_VER

cascade_ui = APIRouter()

_PAGE_PATH = Path(__file__).parent / "assets" / "cascade" / "page.html"


@cascade_ui.get("/", response_class=HTMLResponse)
def cascade_page():
    return Template(_PAGE_PATH.read_text()).safe_substitute(
        react_ver=REACT_VER,
        vb_react_ver=VB_REACT_VER,
        vb_sdk_ver=VB_SDK_VER,
    )
