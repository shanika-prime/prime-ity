"""
Post-extraction validation and normalization.

The model's raw output is never trusted as-is. Every field is coerced to a
string, whitespace-normalized, and — where the field has a known format
(IATA codes, flight numbers, times, dates, PNRs) — validated against that
format. Values that can be safely normalized are cleaned up; values that
fail validation outright are blanked rather than shown wrong, because the
review UI makes a blank field obvious while a plausible-looking wrong value
slips through.
"""
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

STRING_FIELDS = [
    "airline", "flight_number", "cabin_class",
    "departure_airport_code", "departure_city", "departure_date",
    "departure_time", "departure_terminal",
    "arrival_airport_code", "arrival_city", "arrival_date",
    "arrival_time", "arrival_terminal",
    "duration", "stops", "baggage", "pnr", "seat",
]


def _s(value) -> str:
    """Coerce any value to a clean single-spaced string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_airport_code(value: str) -> str:
    """IATA airport codes are exactly 3 A-Z letters. Uppercase and validate;
    blank anything that doesn't fit rather than display a wrong code."""
    v = _s(value).upper()
    v = re.sub(r"[^A-Z]", "", v)
    if re.fullmatch(r"[A-Z]{3}", v):
        return v
    if v:
        logger.warning("Dropping invalid airport code: %r", value)
    return ""


def normalize_flight_number(value: str) -> str:
    """Flight numbers: 2-3 char airline designator (letters/digits, at least
    one letter) + 1-4 digit number, e.g. UL225, EK 655, 3K571. Normalizes
    spacing to 'XX 123'. Tries the (far more common) 2-char designator first
    so 'UL225' parses as UL+225, not UL2+25. Leaves unusual-but-nonempty
    values untouched rather than blanking them."""
    v = _s(value).upper()
    for designator_len in (2, 3):
        m = re.fullmatch(
            rf"([A-Z0-9]{{{designator_len}}})\s*[- ]?\s*(\d{{1,4}})([A-Z]?)", v
        )
        if m and re.search(r"[A-Z]", m.group(1)):
            return f"{m.group(1)} {m.group(2)}{m.group(3)}"
    return v  # keep as-is; review UI lets the user correct it


def normalize_time(value: str) -> str:
    """Normalizes times to 24h HH:MM. Handles '2:15', '02.15', '0215',
    '2:15 PM', '14h35'. Blank if it can't be parsed into a valid time."""
    v = _s(value)
    if not v:
        return ""
    vu = v.upper()
    ampm = None
    if "AM" in vu or "PM" in vu:
        ampm = "PM" if "PM" in vu else "AM"
        vu = vu.replace("A.M.", "").replace("P.M.", "").replace("AM", "").replace("PM", "").strip()
    m = re.fullmatch(r"(\d{1,2})[:.hH]?(\d{2})", vu.replace(" ", ""))
    if not m:
        logger.warning("Dropping unparseable time: %r", value)
        return ""
    hh, mm = int(m.group(1)), int(m.group(2))
    if ampm == "PM" and hh < 12:
        hh += 12
    if ampm == "AM" and hh == 12:
        hh = 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        logger.warning("Dropping out-of-range time: %r", value)
        return ""
    return f"{hh:02d}:{mm:02d}"


def _is_plausible_year(y: int) -> bool:
    """This app processes current/upcoming travel bookings, so a year more
    than a year in the past — or too far in the future — is almost
    certainly a hallucinated default (vision models tend to fall back on a
    "safe" year from their own training data when the year isn't clearly
    legible in the image) rather than something actually read from the
    source."""
    now_year = datetime.now().year
    return (now_year - 1) <= y <= (now_year + 2)


def _resolve_missing_year(mo: int, d: int) -> int:
    """Picks a year when the source doesn't show one (or shows an
    implausible one): the current year, unless that combination of
    month/day has already passed by more than a month, in which case next
    year is the far more sensible guess — this app is for upcoming travel,
    not the past."""
    today = datetime.now()
    year = today.year
    try:
        candidate = datetime(year, mo, d)
    except ValueError:
        return year  # invalid day/month combo (e.g. Feb 30) - let the caller handle it
    if (today - candidate).days > 30:
        year += 1
    return year


def _date_result(y, mo: int, d: int, raw: str) -> str:
    """Builds the final normalized date string. If the year is missing or
    isn't plausible for a current/upcoming booking, a sensible year is
    filled in (see _resolve_missing_year) rather than showing a
    confidently-wrong one like "2024-08-14" when the source never actually
    showed 2024, or dropping the year and showing no date at all."""
    if y is not None and _is_plausible_year(y):
        return f"{y:04d}-{mo:02d}-{d:02d}"
    resolved = _resolve_missing_year(mo, d)
    if y is not None:
        logger.warning("Dropping implausible year %d from %r; using %d instead", y, raw, resolved)
    return f"{resolved:04d}-{mo:02d}-{d:02d}"


def normalize_date(value: str) -> str:
    """Normalizes dates to YYYY-MM-DD. Handles '2026-08-14', '14 Aug 2026',
    'Aug 14, 2026', '14/08/2026' (day-first assumed, as is standard on
    airline documents), and bare day+month with no year at all ('14 Aug').
    A year that isn't plausible for a current/upcoming booking — or that's
    missing entirely — is replaced with a sensible current/next year (see
    _resolve_missing_year) rather than trusted or left blank."""
    v = _s(value)
    if not v:
        return ""
    # Already ISO
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return _date_result(y, mo, d, v)
        return ""
    # '14 Aug 2026' / 'Aug 14, 2026' / '14 August 2026'
    m = re.search(r"(\d{1,2})\s*([A-Za-z]{3,9}),?\s*(\d{4})", v)
    if not m:
        m2 = re.search(r"([A-Za-z]{3,9})\s*(\d{1,2}),?\s*(\d{4})", v)
        if m2:
            mon_txt, d_txt, y_txt = m2.group(1), m2.group(2), m2.group(3)
        else:
            mon_txt = d_txt = y_txt = None
    else:
        d_txt, mon_txt, y_txt = m.group(1), m.group(2), m.group(3)
    if mon_txt:
        mo = _MONTHS.get(mon_txt.lower()[:3])
        if mo:
            d, y = int(d_txt), int(y_txt)
            if 1 <= d <= 31:
                return _date_result(y, mo, d, v)
    # '14/08/2026' or '14-08-2026' - airline docs are day-first
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", v)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # If "day" can only be a month and "month" can't, it was month-first
        if mo > 12 and d <= 12:
            d, mo = mo, d
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return _date_result(y, mo, d, v)
    # 'DD Mon' / 'Mon DD' with no year at all - fill one in
    m = re.fullmatch(r"(\d{1,2})\s*([A-Za-z]{3,9})", v)
    if not m:
        m2 = re.fullmatch(r"([A-Za-z]{3,9})\s*(\d{1,2})", v)
        if m2:
            mon_txt, d_txt = m2.group(1), m2.group(2)
        else:
            mon_txt = d_txt = None
    else:
        d_txt, mon_txt = m.group(1), m.group(2)
    if mon_txt:
        mo = _MONTHS.get(mon_txt.lower()[:3])
        if mo:
            d = int(d_txt)
            if 1 <= d <= 31:
                return _date_result(None, mo, d, v)
    # Genuinely unrecognized: keep cleaned text, don't guess
    return v


def normalize_pnr(value: str) -> str:
    """PNRs are 5-8 alphanumeric characters (6 is most common). Uppercases
    and strips separators; keeps unusual values as-is for manual review."""
    v = re.sub(r"[^A-Za-z0-9]", "", _s(value)).upper()
    return v


def validate_segment(seg: dict) -> dict:
    """Returns a cleaned copy of a segment with every known field coerced,
    normalized, and format-checked. Unknown keys are dropped."""
    if not isinstance(seg, dict):
        return {}
    out = {}
    for key in STRING_FIELDS:
        out[key] = _s(seg.get(key))

    out["departure_airport_code"] = normalize_airport_code(out["departure_airport_code"])
    out["arrival_airport_code"] = normalize_airport_code(out["arrival_airport_code"])
    out["flight_number"] = normalize_flight_number(out["flight_number"])
    out["departure_time"] = normalize_time(out["departure_time"])
    out["arrival_time"] = normalize_time(out["arrival_time"])
    out["departure_date"] = normalize_date(out["departure_date"])
    out["arrival_date"] = normalize_date(out["arrival_date"])
    out["pnr"] = normalize_pnr(out["pnr"])

    # A segment with no route and no flight number is noise, not data
    if not (out["departure_airport_code"] or out["arrival_airport_code"] or out["flight_number"]):
        return {}
    return out


def validate_segments(segments) -> list:
    """Validates a list of raw model-output segments, dropping empties."""
    if not isinstance(segments, list):
        return []
    cleaned = []
    for seg in segments:
        v = validate_segment(seg)
        if v:
            cleaned.append(v)
    return cleaned
