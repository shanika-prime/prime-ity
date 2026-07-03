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


def _leg_block(seg: dict, index: int, total: int) -> str:
    dep_code = seg.get("departure_airport_code", "") or "?"
    arr_code = seg.get("arrival_airport_code", "") or "?"
    airline = seg.get("airline", "")
    flight_no = seg.get("flight_number", "")
    dep_date = _fmt_date(seg.get("departure_date", ""))
    dep_time = seg.get("departure_time", "")
    arr_time = seg.get("arrival_time", "")
    arr_date = _fmt_date(seg.get("arrival_date", ""))
    stops = seg.get("stops", "") or "Non-stop"
    cabin = seg.get("cabin_class", "")
    baggage = seg.get("baggage", "")
    pnr = seg.get("pnr", "")

    header = f"*Leg {index}: {dep_code} → {arr_code}*" if total > 1 else f"*{dep_code} → {arr_code}*"
    lines = [header]

    line1 = " | ".join([p for p in [airline, flight_no] if p])
    if line1:
        lines.append(line1)

    dep_str = f"{dep_date} {dep_time}".strip()
    arr_str = f"{arr_date} {arr_time}".strip()
    if dep_str or arr_str:
        lines.append(f"Dep {dep_str} → Arr {arr_str}".strip())

    tail_bits = [b for b in [stops, cabin] if b]
    if tail_bits:
        lines.append(" | ".join(tail_bits))

    footer_bits = []
    if pnr:
        footer_bits.append(f"PNR: {pnr}")
    if baggage:
        footer_bits.append(f"Baggage: {baggage}")
    if footer_bits:
        lines.append(" | ".join(footer_bits))

    return "\n".join(lines)


def build_whatsapp_message(passenger_name: str, trip_type: str, segments: list) -> str:
    parts = [f"*Flight Itinerary – {passenger_name}*", f"Trip: {trip_type}", ""]
    total = len(segments)
    for i, seg in enumerate(segments, start=1):
        parts.append(_leg_block(seg, i, total))
        parts.append("")
    parts.append("_Subject to airline confirmation._")
    # collapse accidental extra blank lines, keep single blank lines between legs
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text
