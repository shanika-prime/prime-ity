"""
Builds a short, WhatsApp-ready text summary from merged flight segments.
Uses WhatsApp's own formatting syntax (*bold*).

Layout (full mode):
    🛫 *Emirates EK 649 — Flight 1*
    14 Aug  🕑 02:15 → 05:10
    Colombo → Dubai
    🎫 XJ7KQP

    ••••••••••
    Transit 3h 05m @ Dubai
    ••••••••••

    🛫 *Emirates EK 001 — Flight 2*
    ...
    Baggage / meal options (from the form)

Short mode (build_whatsapp_message(..., short=True)) drops only the
departure/arrival clock times — date, route, transit duration, and PNR all
stay, since those are what makes the message "understandable at a glance"
rather than a stripped-down stub.

Transit blocks are inserted *between* consecutive flights when they connect
(arrival airport == next departure airport within a short window). Airport
codes and the raw "stops" text extracted from the source are intentionally
NOT shown — routes are shown as city → city instead.
"""
import re

from journey_utils import s as _s, transit_gap, country_name


def _fmt_date(d: str) -> str:
    """Best-effort trim of a YYYY-MM-DD date to something shorter (14 Aug),
    falls back to the raw string if it isn't in that format."""
    if not d:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", d.strip())
    if not m:
        return d
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    y, mo, day = m.groups()
    try:
        return f"{int(day)} {months[int(mo) - 1]}"
    except (IndexError, ValueError):
        return d


def _place_name(code: str, city: str) -> str:
    """City name is what's shown for a route. Falls back to the (derived)
    country name if the city wasn't extracted, then to '?' — never falls
    back to showing the airport code itself."""
    city = (city or "").strip()
    if city:
        return city
    return country_name(code) or "?"


def _transit_line(prev_seg: dict, next_seg: dict):
    """Builds the compact WhatsApp transit line, e.g. "Transit 3h 05m @
    Dubai". Duration is always included when known — short mode only drops
    per-flight clock times, not this. Returns None if the two flights
    don't connect."""
    gap = transit_gap(prev_seg, next_seg)
    if gap is None:
        return None
    place = _place_name(gap["code"], gap["city"])
    if gap["duration"]:
        return f"Transit {gap['duration']} @ {place}"
    return f"Transit @ {place}"


def _leg_block(seg: dict, index: int, total: int, short: bool = False) -> str:
    dep_code = _s(seg.get("departure_airport_code"))
    arr_code = _s(seg.get("arrival_airport_code"))
    dep_place = _place_name(dep_code, _s(seg.get("departure_city")))
    arr_place = _place_name(arr_code, _s(seg.get("arrival_city")))
    airline = _s(seg.get("airline"))
    flight_no = _s(seg.get("flight_number"))
    dep_date = _fmt_date(_s(seg.get("departure_date")))
    dep_time = _s(seg.get("departure_time"))
    arr_time = _s(seg.get("arrival_time"))
    arr_date = _fmt_date(_s(seg.get("arrival_date")))
    pnr = _s(seg.get("pnr"))
    seat = _s(seg.get("seat"))

    # Flight name (airline + flight number) leads, since that's what
    # identifies the flight — the order label goes on its own line right
    # after, and only when there's more than one flight to distinguish.
    flight_name = " ".join(p for p in [airline, flight_no] if p) or f"Flight {index}"
    header = f"🛫 *{flight_name}*"
    lines = [header]
    if total > 1:
        lines.append(f"Flight {index}")

    if dep_date or arr_date:
        if short:
            # Date stays in short mode; only the clock times drop.
            if dep_date and arr_date and dep_date != arr_date:
                lines.append(f"{dep_date} → {arr_date}")
            else:
                lines.append(dep_date or arr_date)
        else:
            if dep_date and arr_date and dep_date != arr_date:
                lines.append(f"{dep_date} {dep_time} → {arr_date} {arr_time}".strip())
            else:
                date_part = dep_date or arr_date
                time_part = f"{dep_time} → {arr_time}".strip(" →")
                lines.append("  ".join(p for p in [date_part, f"🕑 {time_part}" if time_part else ""] if p))

    lines.append(f"{dep_place} → {arr_place}")

    # Note: airport codes and the extracted "stops" text are intentionally
    # not displayed; transits are shown structurally between flight blocks,
    # and cabin/class is intentionally omitted from the message.

    footer_bits = []
    if pnr:
        footer_bits.append(f"🎫 {pnr}")
    if seat:
        footer_bits.append(f"💺 {seat}")
    if footer_bits:
        lines.append("  ".join(footer_bits))

    return "\n".join(lines)


def _options_lines(options: dict) -> list:
    """Builds the trip-level baggage/meal lines from the form selections."""
    if not options:
        return []
    lines = []
    if options.get("checked_baggage"):
        kg = _s(options.get("checked_baggage_kg")) or "30"
        lines.append(f"🧳 Checked baggage: {kg}kg")
    if options.get("carry_on"):
        kg = _s(options.get("carry_on_kg")) or "7"
        lines.append(f"🎒 Carry-on baggage: {kg}kg")
    if options.get("meal"):
        lines.append("🍽️ Meal included")
    return lines


def build_whatsapp_message(trip_type: str, segments: list, options: dict = None,
                            heading: str = None, short: bool = False) -> str:
    """Builds one message. `heading` overrides the default header — used
    for the separate Onward / Return boxes on round trips. `short=True`
    drops per-flight clock times only (date, route, transit duration, and
    PNR stay)."""
    if heading:
        parts = [heading, ""]
    else:
        parts = [f"Trip: {trip_type}", ""]
    total = len(segments)
    dot_line = "•" * 10

    for i, seg in enumerate(segments):
        parts.append(_leg_block(seg, i + 1, total, short=short))
        # Transit block between this flight and the next, when they connect —
        # separated from both flights by a blank line for readability.
        if i + 1 < total:
            transit = _transit_line(seg, segments[i + 1])
            if transit:
                parts.append("")
                parts.append(dot_line)
                parts.append(transit)
                parts.append(dot_line)
                parts.append("")
            else:
                parts.append("")

    opt_lines = _options_lines(options)
    if opt_lines:
        parts.append("")
        parts.extend(opt_lines)

    # collapse accidental extra blank lines
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text
