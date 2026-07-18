"""Email bodies for the agent's email offers — Phase 40.

Pure builders, no I/O and no env reads (the call_purposes precedent):
callers do the repository reads off the event loop and pass loaded models
in, so building an email can never block and a build failure is the
caller's to swallow. Two emails, mirroring what the agent speaks:

- the itinerary email (the booking-call offer) — the booked flight with
  its rich stamped fields plus whatever build-out items exist at send time;
- the repair email (the Call 2 offer) — the rebooked flight, the original
  as a struck-through "Was …" line from details.rebooked_from, the other
  legs' outcomes, and the PayPal refund sentence when one fired.

Copy rules match the spoken register: airline names never codes, clocks
labeled "PT", rounded prices, short sentences — and nothing an outbound-
only mailbox can't honor: no URLs, no "reply to this email". Simple inline
styles only (interview decision); the text variant mirrors the HTML line
for line. Every field degrades to omission, never a crash — the builders
must work on seed trips and pre-Phase-33 rows.
"""
import html
from datetime import datetime, timezone
from typing import Dict, List, NamedTuple, Optional

from api.call_purposes import _city, _flight_route
from api.flight_options import _PACIFIC, fmt_duration
from api.repositories.models import ItineraryItem, Trip

_ACCENT = "#0f766e"
_MUTED = "#5f6b6a"

# Item type → email label. Title-case display labels, not the call scripts'
# spoken "the …" phrases — an email line reads like a receipt, not a sentence.
_ITEM_LABELS = {
    "hotel": "Hotel",
    "ground": "Airport ride",
    "dining": "Dinner reservation",
    "experience": "Tour",
}

# Item status → the short outcome word a repair email shows per leg.
_STATUS_LABELS = {
    "planned": "planned",
    "booked": "confirmed",
    "broken": "still being worked on",
    "repairing": "still being worked on",
    "fixed": "re-checked and confirmed",
    "cancelled": "cancelled",
}


class EmailContent(NamedTuple):
    subject: str
    html: str
    text: str


def _pt_clock(ts: Optional[datetime]) -> Optional[str]:
    """A UTC instant as the Pacific wall clock the demo speaks — '8:05 AM
    PT' (the standing Phase 19 discipline: the database stores UTC, the
    edges speak Pacific, labeled PT, never PST)."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone(_PACIFIC)
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    clock = f"{hour12}:{local.minute:02d} {ampm}" if local.minute else f"{hour12} {ampm}"
    return f"{clock} PT"


def _pt_date(ts: datetime) -> str:
    """'July 21, 2026' — written dates for email, from the PT calendar."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone(_PACIFIC)
    return f"{local:%B} {local.day}, {local.year}"


def _price_label(price: Optional[float], currency: Optional[str]) -> Optional[str]:
    """'$214' — rounded like the spoken price; non-USD names its currency."""
    if price is None:
        return None
    amount = f"{round(price):,}"
    if currency and currency != "USD":
        return f"{amount} {currency}"
    return f"${amount}"


def _flight_identity(details: dict) -> Optional[str]:
    """'Delta 439' from the stamped rich fields — the displayed name first
    (Phase 33), the bare code as the degraded fallback, None when the row
    carries no identity at all (seed trips)."""
    carrier = details.get("airline_name") or details.get("airline")
    number = details.get("flight_number")
    if carrier and number:
        return f"{carrier} {number}"
    return carrier or None


def _flight_facts(flight: ItineraryItem) -> List[str]:
    """The flight's fact lines, from the same stamped `details` the cascade
    card renders — each line present only when its data is (the Phase 33
    degrade-to-omission rule)."""
    details = flight.details or {}
    lines: List[str] = []

    identity_parts = []
    identity = _flight_identity(details)
    if identity:
        identity_parts.append(identity)
    if details.get("cabin"):
        identity_parts.append(str(details["cabin"]))
    if details.get("duration_minutes"):
        identity_parts.append(fmt_duration(details["duration_minutes"]))
    if identity_parts:
        lines.append(" · ".join(identity_parts))

    if flight.start_ts:
        depart = f"Departs {_pt_date(flight.start_ts)} at {_pt_clock(flight.start_ts)}"
        if flight.end_ts:
            depart += f", lands {_pt_clock(flight.end_ts)}"
            if details.get("arrives_next_day"):
                depart += " the next day"
        lines.append(depart)

    layovers = details.get("layover_airports") or []
    if layovers:
        lines.append("Connects in " + ", ".join(_city(code) for code in layovers))
    elif details.get("stops") == 0:
        lines.append("Nonstop")

    price = _price_label(flight.price, flight.currency)
    if price:
        lines.append(price)
    return lines


def _was_line(flight: ItineraryItem) -> Optional[str]:
    """The original flight from details.rebooked_from — 'Was Delta 439 ·
    departed 8:05 AM · $214', degrading to whatever fields the stamp
    carries (the Phase 32 was-line rule), None when there is nothing
    meaningful to say."""
    original = (flight.details or {}).get("rebooked_from") or {}
    parts = []
    identity = _flight_identity(original)
    if identity:
        parts.append(identity)
    if original.get("depart_time"):
        parts.append(f"departed {original['depart_time']}")
    price = _price_label(original.get("price"), original.get("currency"))
    if price:
        parts.append(price)
    if not parts:
        return None
    return "Was " + " · ".join(str(p) for p in parts)


def _route_heading(flight: Optional[ItineraryItem], trip: Trip) -> str:
    """'Flight — New York to Los Angeles', falling back to just 'Flight'
    when the trip carries no route at all."""
    origin, dest = _flight_route(flight, trip)
    if origin and dest:
        return f"Flight — {_city(origin)} to {_city(dest)}"
    return "Flight"


def _item_line(item: ItineraryItem, status_word: Optional[str] = None) -> str:
    """One build-out leg as a receipt line: 'Hotel — Hotel in LAX, July 21,
    2026 · $412'. status_word (repair email) appends the leg's outcome."""
    label = _ITEM_LABELS.get(item.type, item.type.title())
    parts = [label]
    if item.location:
        parts[0] = f"{label} — {item.location}"
    if item.start_ts:
        parts.append(_pt_date(item.start_ts))
    price = _price_label(item.price, item.currency)
    if price:
        parts.append(price)
    line = ", ".join(parts)
    if status_word:
        line += f" ({status_word})"
    return line


def _destination_city(trip: Trip, flight: Optional[ItineraryItem]) -> Optional[str]:
    _, dest = _flight_route(flight, trip)
    return _city(dest) if dest else None


def _render(
    subject: str,
    intro: str,
    flight_heading: str,
    flight_lines: List[str],
    was: Optional[str],
    item_lines: List[str],
    extra_paragraphs: List[str],
) -> EmailContent:
    """One layout for both emails: intro, the flight card, the other legs,
    closing paragraphs, a plain sign-off. Dynamic values are escaped for
    the HTML variant; the text variant mirrors it line for line."""
    esc = html.escape

    html_parts = [
        f'<div style="font-family: -apple-system, Segoe UI, Roboto, '
        f'Helvetica, Arial, sans-serif; color: #1f2a2a; max-width: 560px; '
        f'margin: 0 auto; padding: 16px;">',
        f'<h2 style="color: {_ACCENT}; margin: 0 0 4px;">{esc(subject)}</h2>',
        f'<p style="margin: 8px 0 16px;">{esc(intro)}</p>',
        f'<div style="border-left: 3px solid {_ACCENT}; padding: 8px 12px; '
        f'margin: 0 0 16px; background: #f6f8f8;">',
        f'<strong>{esc(flight_heading)}</strong>',
    ]
    for line in flight_lines:
        html_parts.append(f'<br>{esc(line)}')
    if was:
        html_parts.append(
            f'<br><s style="color: {_MUTED};">{esc(was)}</s>'
        )
    html_parts.append("</div>")
    if item_lines:
        html_parts.append('<ul style="margin: 0 0 16px; padding-left: 20px;">')
        for line in item_lines:
            html_parts.append(f'<li style="margin: 2px 0;">{esc(line)}</li>')
        html_parts.append("</ul>")
    for paragraph in extra_paragraphs:
        html_parts.append(f'<p style="margin: 0 0 12px;">{esc(paragraph)}</p>')
    html_parts.append(
        f'<p style="color: {_MUTED}; margin: 16px 0 0;">— Cascade</p>'
    )
    html_parts.append("</div>")

    text_lines = [subject, "", intro, "", flight_heading]
    text_lines.extend(f"  {line}" for line in flight_lines)
    if was:
        text_lines.append(f"  {was}")
    if item_lines:
        text_lines.append("")
        text_lines.extend(f"- {line}" for line in item_lines)
    for paragraph in extra_paragraphs:
        text_lines.extend(["", paragraph])
    text_lines.extend(["", "— Cascade"])

    return EmailContent(
        subject=subject, html="".join(html_parts), text="\n".join(text_lines)
    )


def build_itinerary_email(trip: Trip, items: List[ItineraryItem]) -> EmailContent:
    """The booking-call email: the booked trip as it stands at send time —
    the flight card plus one line per build-out item that already exists
    (a yes spoken right after book_flight may email just the flight)."""
    flight = next((i for i in items if i.type == "flight"), None)
    dest = _destination_city(trip, flight)
    subject = f"Your trip to {dest}" if dest else f"Your trip: {trip.title}"

    when = ""
    if trip.start_date and trip.end_date:
        when = (
            f" from {trip.start_date:%B} {trip.start_date.day} to "
            f"{trip.end_date:%B} {trip.end_date.day}"
        )
    intro = f"Here's everything on your booked trip{when}, all in one place."

    flight_lines = _flight_facts(flight) if flight else []
    item_lines = [_item_line(i) for i in items if i.type != "flight"]
    return _render(
        subject=subject,
        intro=intro,
        flight_heading=_route_heading(flight, trip),
        flight_lines=flight_lines,
        was=None,
        item_lines=item_lines,
        extra_paragraphs=[],
    )


def build_repair_email(
    trip: Trip,
    items: List[ItineraryItem],
    details: Dict[str, dict],
    refund_line: Optional[str] = None,
) -> EmailContent:
    """The Call 2 email: the repair summary, consistent with what the call
    speaks — the rebooked flight (with the original struck through), each
    other leg's outcome, the why-chosen sentence from the detail payload,
    and the refund sentence when one fired."""
    flight = next((i for i in items if i.type == "flight"), None)
    dest = _destination_city(trip, flight)
    fixed = flight is not None and flight.status == "fixed"
    # The subject stays honest with the live state — never "fixed" over a
    # repair still in flight (the trip_status all-clear rule, applied here).
    if fixed:
        subject = f"Your trip to {dest} is fixed" if dest else "Your trip is fixed"
        intro = (
            "Your flight was cancelled, and your trip is repaired — "
            "here's where everything landed."
        )
    else:
        subject = (
            f"Update on your trip to {dest}" if dest else "Update on your trip"
        )
        intro = (
            "Your flight was cancelled — here's where the repair stands "
            "right now."
        )

    flight_lines = _flight_facts(flight) if flight else []
    item_lines = [
        _item_line(i, _STATUS_LABELS.get(i.status, i.status))
        for i in items
        if i.type != "flight"
    ]

    extra: List[str] = []
    detail = details.get(flight.item_id, {}) if flight else {}
    why = (detail.get("why_chosen") or "").strip()
    if why:
        extra.append(why)
    if refund_line:
        extra.append(refund_line)

    return _render(
        subject=subject,
        intro=intro,
        flight_heading=_route_heading(flight, trip),
        flight_lines=flight_lines,
        was=_was_line(flight) if flight else None,
        item_lines=item_lines,
        extra_paragraphs=extra,
    )
