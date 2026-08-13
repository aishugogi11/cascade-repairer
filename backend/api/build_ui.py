"""Optimize My Trip page shell — same conventions as cascade_ui."""
from pathlib import Path
from string import Template

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.web_call import REACT_VER, VB_REACT_VER, VB_SDK_VER

build_ui = APIRouter()

_PAGE_PATH = Path(__file__).parent / "assets" / "build" / "page.html"


@build_ui.get("/", response_class=HTMLResponse)
def build_page():
    return Template(_PAGE_PATH.read_text(encoding="utf-8")).safe_substitute(
        react_ver=REACT_VER,
        vb_react_ver=VB_REACT_VER,
        vb_sdk_ver=VB_SDK_VER,
    )
