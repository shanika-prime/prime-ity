"""
Shared journey and transit-detection logic used by both text_gen.py
(WhatsApp output) and pdf_gen.py (PDF output), so the two outputs always
agree on what counts as a connection/transit between flights.

Transit is computed structurally (matching arrival/departure airports +
plausible time gap) rather than trusted from the extracted "stops" text —
the model's free-text description of stops is inconsistent, but airport
codes and timestamps are the fields validate.py already normalizes and
checks, so computing from them is far more reliable.
"""
import re
from datetime import datetime

# A connection is treated as a transit only when the gap between arrival and
# the next departure is within this window. Longer gaps (e.g. the days
# between a round trip's outbound and return) are a new journey, not a
# transit within one.
MAX_TRANSIT_HOURS = 24

# Common IATA airport codes -> country name, covering the routes a Sri
# Lanka-based travel agency deals with most: South Asia, the Gulf/Middle
# East, Southeast/East Asia, Europe, and North America. Deriving country
# from the (already validated) airport code is far more reliable than
# asking the model to also infer/output a country name.
IATA_COUNTRY = {
    # Sri Lanka
    "CMB": "Sri Lanka", "HRI": "Sri Lanka", "JAF": "Sri Lanka",
    # India
    "DEL": "India", "BOM": "India", "MAA": "India", "BLR": "India",
    "HYD": "India", "CCU": "India", "COK": "India", "TRV": "India",
    "GOI": "India", "AMD": "India", "PNQ": "India",
    # South Asia
    "MLE": "Maldives", "KTM": "Nepal", "DAC": "Bangladesh",
    "CGP": "Bangladesh", "ISB": "Pakistan", "KHI": "Pakistan", "LHE": "Pakistan",
    # Gulf / Middle East
    "DXB": "United Arab Emirates", "AUH": "United Arab Emirates",
    "SHJ": "United Arab Emirates", "DOH": "Qatar", "BAH": "Bahrain",
    "KWI": "Kuwait", "MCT": "Oman", "RUH": "Saudi Arabia", "JED": "Saudi Arabia",
    "DMM": "Saudi Arabia", "MED": "Saudi Arabia", "AMM": "Jordan",
    "BEY": "Lebanon", "TLV": "Israel", "CAI": "Egypt",
    # Southeast Asia
    "SIN": "Singapore", "KUL": "Malaysia", "PEN": "Malaysia",
    "BKK": "Thailand", "DMK": "Thailand", "HKT": "Thailand",
    "CGK": "Indonesia", "DPS": "Indonesia", "MNL": "Philippines",
    "CEB": "Philippines", "SGN": "Vietnam", "HAN": "Vietnam",
    "RGN": "Myanmar", "PNH": "Cambodia",
    # East Asia
    "HKG": "Hong Kong", "TPE": "Taiwan", "ICN": "South Korea",
    "GMP": "South Korea", "NRT": "Japan", "HND": "Japan", "KIX": "Japan",
    "PEK": "China", "PVG": "China", "CAN": "China", "SZX": "China",
    # Europe
    "LHR": "United Kingdom", "LGW": "United Kingdom", "MAN": "United Kingdom",
    "CDG": "France", "ORY": "France", "FRA": "Germany", "MUC": "Germany",
    "AMS": "Netherlands", "FCO": "Italy", "MXP": "Italy", "MAD": "Spain",
    "BCN": "Spain", "ZRH": "Switzerland", "GVA": "Switzerland",
    "VIE": "Austria", "BRU": "Belgium", "CPH": "Denmark", "OSL": "Norway",
    "ARN": "Sweden", "HEL": "Finland", "IST": "Turkey", "SAW": "Turkey",
    "ATH": "Greece", "LIS": "Portugal", "DUB": "Ireland", "WAW": "Poland",
    # North America
    "JFK": "United States", "EWR": "United States", "LAX": "United States",
    "ORD": "United States", "SFO": "United States", "SEA": "United States",
    "IAD": "United States", "BOS": "United States", "MIA": "United States",
    "ATL": "United States", "DFW": "United States", "IAH": "United States",
    "YYZ": "Canada", "YVR": "Canada", "YUL": "Canada",
    # Australia / NZ
    "SYD": "Australia", "MEL": "Australia", "BNE": "Australia",
    "PER": "Australia", "AKL": "New Zealand",
    # Africa
    "JNB": "South Africa", "CPT": "South Africa", "NBO": "Kenya",
    "ADD": "Ethiopia", "LOS": "Nigeria",
}


def country_name(code: str, fallback_city: str = "") -> str:
    """Looks up the country for an IATA airport code. Falls back to the
    given city name if the code isn't in the lookup, then to "" — never
    falls back to showing the airport code itself."""
    code = (code or "").strip().upper()
    if code in IATA_COUNTRY:
        return IATA_COUNTRY[code]
    return (fallback_city or "").strip()


def s(value) -> str:
    """Coerces any value to a plain string. The model is asked to return
    strings for every field, but isn't 100% reliable — if it ever returns a
    number, list, or nested object instead, this stops that from crashing
    string formatting downstream."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def parse_dt(date_str: str, time_str: str):
    """Parses a validated YYYY-MM-DD date + HH:MM time into a datetime.
    Returns None if either part isn't in the expected normalized format."""
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None


def transit_gap(prev_seg: dict, next_seg: dict):
    """Returns {"code": str, "city": str, "duration": str|None} if next_seg
    departs from where prev_seg arrived (a connection), else None. This is
    the detection logic; callers format the display text themselves (e.g.
    pdf_gen.py shows the code, text_gen.py shows the country instead)."""
    arr_code = s(prev_seg.get("arrival_airport_code"))
    dep_code = s(next_seg.get("departure_airport_code"))
    if not arr_code or arr_code != dep_code:
        return None

    city = s(prev_seg.get("arrival_city"))

    arr_dt = parse_dt(s(prev_seg.get("arrival_date")), s(prev_seg.get("arrival_time")))
    dep_dt = parse_dt(s(next_seg.get("departure_date")), s(next_seg.get("departure_time")))

    if arr_dt and dep_dt:
        gap_min = (dep_dt - arr_dt).total_seconds() / 60
        if gap_min <= 0 or gap_min > MAX_TRANSIT_HOURS * 60:
            # Same airport but implausible gap: a return leg days later,
            # or bad data — either way, not a transit.
            return None
        h, m = divmod(int(gap_min), 60)
        duration = f"{h}h {m:02d}m" if h else f"{m}m"
        return {"code": arr_code, "city": city, "duration": duration}

    # Times unknown: only call it a transit when both are on the same day,
    # otherwise (or with no dates at all) don't guess.
    prev_date = s(prev_seg.get("arrival_date"))
    next_date = s(next_seg.get("departure_date"))
    if prev_date and prev_date == next_date:
        return {"code": arr_code, "city": city, "duration": None}
    return None


def transit_between(prev_seg: dict, next_seg: dict):
    """Formatted transit line using the airport code (+ city if known) —
    e.g. "Transit at DXB (Dubai) — 3h 05m". Used by pdf_gen.py, where
    airport codes are still shown. Returns None if there's no connection."""
    gap = transit_gap(prev_seg, next_seg)
    if gap is None:
        return None
    place = f"{gap['code']} ({gap['city']})" if gap["city"] else gap["code"]
    if gap["duration"]:
        return f"Transit at {place} — {gap['duration']}"
    return f"Transit at {place}"


def group_into_journeys(segments: list) -> list:
    """Splits a chronologically-sorted segment list into journeys: a new
    journey starts whenever two consecutive segments don't connect (a
    round trip's return leg, or separate multi-city hops). Segments are
    assumed already sorted by departure date/time."""
    if not segments:
        return []
    journeys = [[segments[0]]]
    for prev, cur in zip(segments, segments[1:]):
        if transit_between(prev, cur) is not None:
            journeys[-1].append(cur)
        else:
            journeys.append([cur])
    return journeys


def technical_stop_text(stops: str) -> str:
    """Extracts just the 'Technical stop ...' portion of a (possibly
    compound) stops string — e.g. "Technical stop at MLE - 1hr; Layover at
    DOH - 3h 15m" -> "Technical stop at MLE - 1hr". Layover/transfer/transit
    wording is deliberately ignored here since that's computed structurally
    via transit_between() instead; a technical stop is mid-flight (same
    flight number continues) so it can't be derived that way and has to
    come from the extracted text. Returns "" if no technical stop is
    mentioned."""
    if not stops:
        return ""
    parts = re.split(r"[;|]", stops)
    for p in parts:
        if "technical" in p.lower():
            return p.strip()
    return ""
