"""
Builds a short, WhatsApp-ready text summary from merged flight segments and
a passenger name. Uses WhatsApp's own formatting syntax (*bold*) instead of
any PDF/document output.
"""
import re


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


def _s(value) -> str:
    """Coerces any value to a plain string. The model is asked to return
    strings for every field, but isn't 100% reliable — if it ever returns a
    number, list, or nested object instead, this stops that from crashing
    string formatting (e.g. str.join()) downstream."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _leg_block(seg: dict, index: int, total: int) -> str:
    dep_code = _s(seg.get("departure_airport_code")) or "?"
    arr_code = _s(seg.get("arrival_airport_code")) or "?"
    airline = _s(seg.get("airline"))
    flight_no = _s(seg.get("flight_number"))
    dep_date = _fmt_date(_s(seg.get("departure_date")))
    dep_time = _s(seg.get("departure_time"))
    arr_time = _s(seg.get("arrival_time"))
    arr_date = _fmt_date(_s(seg.get("arrival_date")))
    stops = _s(seg.get("stops"))
    cabin = _s(seg.get("cabin_class"))
    baggage = _s(seg.get("baggage"))
    pnr = _s(seg.get("pnr"))
    seat = _s(seg.get("seat"))

    header = (f"🛫 *Flight {index}: {dep_code} → {arr_code}*" if total > 1
              else f"🛫 *{dep_code} → {arr_code}*")
    lines = [header]

    line1 = " | ".join([p for p in [airline, flight_no] if p])
    if line1:
        lines.append(line1)

    # Overnight/multi-day flights show both dates; same-day flights show one
    # date with a time range, which is more compact and still unambiguous.
    if dep_date and arr_date and dep_date != arr_date:
        date_time_line = f"📅 {dep_date} {dep_time} → {arr_date} {arr_time}".strip()
    else:
        date_part = dep_date or arr_date
        time_part = f"{dep_time} → {arr_time}".strip(" →")
        date_time_line = "  ".join(p for p in [f"📅 {date_part}" if date_part else "", f"🕑 {time_part}" if time_part else ""] if p)
    if date_time_line:
        lines.append(date_time_line)

    if stops:
        if "layover" in stops.lower():
            lines.append("..........")
            lines.append(stops)
            lines.append("..........")
        else:
            lines.append(stops)
    if cabin:
        lines.append(cabin)

    footer_bits = []
    if pnr:
        footer_bits.append(f"🎫 {pnr}")
    if baggage:
        footer_bits.append(f"🧳 {baggage}")
    if seat:
        footer_bits.append(f"💺 {seat}")
    if footer_bits:
        lines.append("  ".join(footer_bits))

    return "\n".join(lines)


def build_whatsapp_message(trip_type: str, segments: list) -> str:
    parts = ["✈️ *Flight Details*", f"Trip: {trip_type}", ""]
    total = len(segments)
    for i, seg in enumerate(segments, start=1):
        parts.append(_leg_block(seg, i, total))
        parts.append("")
    # collapse accidental extra blank lines, keep single blank lines between legs
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text
