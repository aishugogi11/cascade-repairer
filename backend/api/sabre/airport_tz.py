"""Static IATA → IANA timezone table for InstaFlights time conversion.

InstaFlights DepartureDateTime/ArrivalDateTime carry no UTC offset — they
are wall clock *at that airport* (sabre-cert-notes.md, delta #5). Speaking
or storing them unconverted repeats the Phase 19 bug class, so the parser
localizes each time to its airport's zone and converts to Pacific before
anything is spoken or written.

Static data in code, no runtime lookup, no new dependency (requirements
§ Stack limits). Coverage is CERT's full supported-markets list, kept in
parity by the cert-marked test in test_sabre_cert.py (Phase 28): every code
the live list carries — including its metro/city codes (NYC, LON, PAR, …)
and non-US airports — resolves here. An airport absent from the table means
the itinerary is skipped in favor of the next (requirements, decision 2) —
an honest miss, never a mangled time.
"""
from typing import Optional
from zoneinfo import ZoneInfo

# IATA code -> IANA zone. Grouped by zone for reviewability.
AIRPORT_TZ: dict = {
    # Eastern (NYC/WAS are the live list's metro codes — Phase 28 parity)
    **{code: "America/New_York" for code in (
        "JFK", "LGA", "EWR", "BOS", "PHL", "BWI", "DCA", "IAD", "ATL",
        "MIA", "FLL", "MCO", "TPA", "PBI", "RSW", "JAX", "CLT", "RDU",
        "GSO", "ORF", "RIC", "PIT", "CLE", "CMH", "CVG", "DAY", "DTW",
        "GRR", "IND", "SDF", "LEX", "BUF", "ROC", "SYR", "ALB", "BDL",
        "PVD", "BTV", "PWM", "CHS", "SAV", "TYS", "CHA", "GSP", "MYR",
        "ABE", "CAK", "HPN", "MDT", "TEB", "ORL", "NYC", "WAS",
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
    # Caribbean / South America (Phase 28 parity — the live list carries
    # them; BUE is Buenos Aires' metro code, riding its city's zone)
    "SJU": "America/Puerto_Rico",
    **{code: "America/Argentina/Buenos_Aires" for code in ("BUE", "EZE")},
    "COR": "America/Argentina/Cordoba",
    # Europe / Russia (Phase 28 parity; LON/PAR/ROM/MIL/STO/MOW are metro)
    **{code: "Europe/London" for code in ("LHR", "LON", "MAN")},
    "PAR": "Europe/Paris",
    "AMS": "Europe/Amsterdam",
    "BRU": "Europe/Brussels",
    **{code: "Europe/Madrid" for code in ("MAD", "BCN")},
    **{code: "Europe/Rome" for code in ("ROM", "MIL")},
    "ATH": "Europe/Athens",
    **{code: "Europe/Stockholm" for code in ("ARN", "STO", "GOT")},
    "CPH": "Europe/Copenhagen",
    "OSL": "Europe/Oslo",
    "MOW": "Europe/Moscow",
}


def airport_zone(code: str) -> Optional[ZoneInfo]:
    """The airport's IANA zone, or None for anything not in the table."""
    name = AIRPORT_TZ.get((code or "").strip().upper())
    return ZoneInfo(name) if name else None
