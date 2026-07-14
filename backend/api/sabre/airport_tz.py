"""Static IATA → IANA timezone table for InstaFlights time conversion.

InstaFlights DepartureDateTime/ArrivalDateTime carry no UTC offset — they
are wall clock *at that airport* (sabre-cert-notes.md, delta #5). Speaking
or storing them unconverted repeats the Phase 19 bug class, so the parser
localizes each time to its airport's zone and converts to Pacific before
anything is spoken or written.

Static data in code, no runtime lookup, no new dependency (requirements
§ Stack limits). Coverage is the majors in CERT's supported-markets list;
an airport absent here means the itinerary is skipped in favor of the next
(requirements, decision 2) — an honest miss, never a mangled time.
"""
from typing import Optional
from zoneinfo import ZoneInfo

# IATA code -> IANA zone. Grouped by zone for reviewability.
AIRPORT_TZ: dict = {
    # Eastern
    **{code: "America/New_York" for code in (
        "JFK", "LGA", "EWR", "BOS", "PHL", "BWI", "DCA", "IAD", "ATL",
        "MIA", "FLL", "MCO", "TPA", "PBI", "RSW", "JAX", "CLT", "RDU",
        "GSO", "ORF", "RIC", "PIT", "CLE", "CMH", "CVG", "DAY", "DTW",
        "GRR", "IND", "SDF", "LEX", "BUF", "ROC", "SYR", "ALB", "BDL",
        "PVD", "BTV", "PWM", "CHS", "SAV", "TYS", "CHA", "GSP", "MYR",
    )},
    # Central
    **{code: "America/Chicago" for code in (
        "ORD", "MDW", "MKE", "MSN", "GRB", "MSP", "DFW", "DAL", "IAH",
        "HOU", "AUS", "SAT", "MSY", "MEM", "BNA", "STL", "MCI", "OKC",
        "TUL", "OMA", "DSM", "ICT", "LIT", "XNA", "BHM", "HSV", "JAN",
        "MOB", "SGF", "FAR", "FSD",
    )},
    # Mountain
    **{code: "America/Denver" for code in (
        "DEN", "COS", "ABQ", "SLC", "BZN", "BIL", "MSO", "GTF", "JAC",
        "RAP", "ELP",
    )},
    "BOI": "America/Boise",
    # Arizona (no DST)
    "PHX": "America/Phoenix",
    "TUS": "America/Phoenix",
    # Pacific
    **{code: "America/Los_Angeles" for code in (
        "LAX", "SFO", "SAN", "SJC", "OAK", "SMF", "BUR", "LGB", "SNA",
        "ONT", "PSP", "FAT", "RNO", "LAS", "SEA", "PDX", "GEG", "EUG",
        "MFR", "BLI",
    )},
    # Alaska / Hawaii
    **{code: "America/Anchorage" for code in ("ANC", "FAI", "JNU")},
    **{code: "Pacific/Honolulu" for code in ("HNL", "OGG", "KOA", "LIH", "ITO")},
}


def airport_zone(code: str) -> Optional[ZoneInfo]:
    """The airport's IANA zone, or None for anything not in the table."""
    name = AIRPORT_TZ.get((code or "").strip().upper())
    return ZoneInfo(name) if name else None
