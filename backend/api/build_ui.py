"""Optimize My Trip page shell — same conventions as cascade_ui."""
from pathlib import Path
from string import Template

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from api.web_call import REACT_VER, VB_REACT_VER, VB_SDK_VER

build_ui = APIRouter()

_ASSETS = Path(__file__).parent / "assets" / "build"
_PAGE_PATH = _ASSETS / "page.html"
_SAMPLE_PDFS = {
    "sf": _ASSETS / "sample_tripwise_itinerary.pdf",
    "nyc": _ASSETS / "sample_nyc_business_itinerary.pdf",
}


@build_ui.get("/", response_class=HTMLResponse)
def build_page():
    return Template(_PAGE_PATH.read_text(encoding="utf-8")).safe_substitute(
        react_ver=REACT_VER,
        vb_react_ver=VB_REACT_VER,
        vb_sdk_ver=VB_SDK_VER,
    )


@build_ui.get("/sample/{kind}.pdf")
def sample_pdf(kind: str):
    """Downloadable sample itineraries for Optimize My Trip demos."""
    path = _SAMPLE_PDFS.get((kind or "").strip().lower())
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="unknown sample itinerary")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
    )
