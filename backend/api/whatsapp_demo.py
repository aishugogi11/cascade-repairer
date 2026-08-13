"""Fake WhatsApp front door for Cascade Repairer.

Not Meta Cloud API. The page pretends to be a WhatsApp chat; ingest
creates a Cascade trip from the uploaded PDF (or the sample itinerary)
so /v1/cascade/?trip_id= shows those legs.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import memory_trips
from api.pdf_itinerary import build_from_upload
from api.sabre_tools import create_seed_trip

whatsapp_demo = APIRouter()


class IngestRequest(BaseModel):
    sample: bool = False
    sample_kind: str = ""
    filename: str = ""
    text: str = ""
    pdf_base64: str = ""


def _count_types(items: list) -> dict:
    counts = {"flight": 0, "hotel": 0, "ground": 0, "dining": 0, "experience": 0}
    for row in items:
        kind = row.get("type")
        if kind in counts:
            counts[kind] += 1
    return counts


def _spoken_counts(counts: dict) -> str:
    labels = {
        "flight": ("flight", "flights"),
        "hotel": ("hotel", "hotels"),
        "ground": ("ride", "rides"),
        "dining": ("dinner", "dinners"),
        "experience": ("experience", "experiences"),
    }
    bits = []
    for key, (one, many) in labels.items():
        n = counts.get(key) or 0
        if n:
            bits.append(f"{n} {one if n == 1 else many}")
    return ", ".join(bits) if bits else "your booked trip"


def _should_try_bigquery() -> bool:
    """Skip the ADC metadata wait when this process clearly has no GCP creds."""
    if os.environ.get("K_SERVICE"):
        return True
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    return bool(path and Path(path).is_file())


def _seed_trip(user_id: str, title: str) -> tuple[dict, str]:
    if _should_try_bigquery():
        try:
            return create_seed_trip(user_id, title), "bigquery"
        except HTTPException:
            pass
        except Exception:  # noqa: BLE001
            pass
    return memory_trips.seed(user_id, title), "memory"


@whatsapp_demo.post("/ingest")
def ingest(req: IngestRequest):
    """Build a Cascade trip from the uploaded PDF, sample text, or seed."""
    name = (req.filename or "").strip()
    title = "WhatsApp trip — Cascade Repairer"
    kind = (req.sample_kind or "").strip().lower()
    if kind == "nyc":
        title = "SFO → New York business trip"
    elif req.sample:
        title = "WhatsApp sample itinerary"
    elif name:
        title = f"WhatsApp trip — {name}"
    try:
        built = build_from_upload(
            user_id="whatsapp-demo",
            title=title,
            sample=req.sample,
            sample_kind=kind,
            text=req.text,
            pdf_base64=req.pdf_base64,
        )
    except Exception:  # noqa: BLE001 — a bad PDF must still open Cascade
        built = None
    if built is not None:
        trip, items = built
        seeded = memory_trips.put(trip, items)
        if req.pdf_base64:
            source = "pdf"
        elif kind == "nyc":
            source = "sample_nyc"
        elif req.sample:
            source = "sample"
        else:
            source = "text"
    else:
        seeded, source = _seed_trip("whatsapp-demo", title)
    trip_id = seeded["trip_id"]
    counts = _count_types(seeded.get("items") or [])
    spoken = _spoken_counts(counts)
    cascade_path = f"/v1/cascade/?trip_id={trip_id}"
    return {
        "ok": True,
        "demo": True,
        "source": source,
        "trip_id": trip_id,
        "cascade_path": cascade_path,
        "counts": counts,
        "spoken_counts": spoken,
        "reply_reviewing": (
            "Got it, reviewing your trip details now. Open the link below "
            "and the details will populate there as I read them. I'll confirm "
            "here when it's done."
        ),
        "reply_done": (
            f"I've read your trip document and noted that it includes {spoken}. "
            "If you'd like to discuss changes, tap Talk on the Cascade page I sent."
        ),
    }
