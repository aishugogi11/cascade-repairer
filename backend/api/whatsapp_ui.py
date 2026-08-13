"""Fake WhatsApp chat shell — same conventions as cascade_ui."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

whatsapp_ui = APIRouter()

_PAGE_PATH = Path(__file__).parent / "assets" / "whatsapp" / "page.html"


@whatsapp_ui.get("/", response_class=HTMLResponse)
def whatsapp_page():
    return HTMLResponse(_PAGE_PATH.read_text(encoding="utf-8"))
