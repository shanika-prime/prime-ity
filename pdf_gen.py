"""
Builds a clean, unbranded travel itinerary PDF from merged flight segments
and passenger name(s), using ReportLab.

Layout adapts to trip type:
- One Way (1 image)         -> flights listed in order, no section headers
- Round Trip (2 images)      -> "Onward Journey" / "Return Journey" sections
- Multi-City (3+ images)     -> "Journey 1", "Journey 2", ... sections

Journeys are detected structurally (see journey_utils.group_into_journeys):
a new journey starts wherever consecutive flights don't connect. Transit
details are shown immediately after the flight card they follow — not
collected into a separate panel — so the itinerary reads top-to-bottom the
same way a person would explain the trip out loud. A technical stop (same
flight, mid-route landing) shows as a small note on that flight's own card,
since it isn't a gap between two segments.
"""
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)

from journey_utils import s as _s, group_into_journeys, transit_between, technical_stop_text

NAVY = colors.HexColor("#10233F")
NAVY_DEEP = colors.HexColor("#0A1830")
AMBER = colors.HexColor("#FFB020")
CARD_BG = colors.HexColor("#EEF1F5")
TRANSIT_BG = colors.HexColor("#FFF6E8")
TEXT_GREY = colors.HexColor("#5B6472")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="DocTitle", fontSize=20, leading=24,
                           textColor=NAVY, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="DocSubtitle", fontSize=12, leading=15,
                           textColor=TEXT_GREY, fontName="Helvetica"))
styles.add(ParagraphStyle(name="PaxLine", fontSize=11, leading=15,
                           textColor=colors.black))
styles.add(ParagraphStyle(name="JourneyHeader", fontSize=11, leading=14,
                           textColor=colors.white, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SegHeader", fontSize=10, leading=13,
                           textColor=colors.white, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SegRoute", fontSize=15, leading=18,
                           fontName="Helvetica-Bold", textColor=NAVY_DEEP))
styles.add(ParagraphStyle(name="SegCities", fontSize=9.5, leading=13,
                           textColor=TEXT_GREY))
styles.add(ParagraphStyle(name="LabelSmall", fontSize=8, leading=10,
                           textColor=TEXT_GREY, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="ValueMed", fontSize=10.5, leading=13,
                           textColor=colors.black, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="MetaLine", fontSize=8.5, leading=11,
                           textColor=TEXT_GREY))
styles.add(ParagraphStyle(name="TechNote", fontSize=8.5, leading=11,
                           textColor=NAVY_DEEP, fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle(name="TransitLine", fontSize=9.5, leading=12,
                           textColor=NAVY_DEEP, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="FooterNote", fontSize=8, leading=10,
                           textColor=TEXT_GREY))


def _journey_header(label: str) -> Table:
    t = Table([[Paragraph(label.upper(), styles["JourneyHeader"])]], colWidths=[160 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _transit_strip(text: str) -> Table:
    """Compact single-line strip shown between two connecting flight cards
    — deliberately lighter weight than a full card so it reads as
    in-between info, not another flight."""
    t = Table([[Paragraph(f"⏱  {text}", styles["TransitLine"])]], colWidths=[160 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TRANSIT_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, AMBER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _segment_card(seg: dict, index: int, total: int) -> Table:
    dep_code = _s(seg.get("departure_airport_code")) or "---"
    arr_code = _s(seg.get("arrival_airport_code")) or "---"
    dep_city = _s(seg.get("departure_city"))
    arr_city = _s(seg.get("arrival_city"))
    airline = _s(seg.get("airline"))
    flight_no = _s(seg.get("flight_number"))

    tag = f"FLIGHT {index}" if total > 1 else "FLIGHT"
    header_text = "  ·  ".join(p for p in [tag, " ".join(p2 for p2 in [airline, flight_no] if p2)] if p)
    seg_header = Table([[Paragraph(header_text, styles["SegHeader"])]], colWidths=[160 * mm])
    seg_header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY_DEEP),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    route = Paragraph(f"{dep_code}  →  {arr_code}", styles["SegRoute"])
    cities = Paragraph(f"{dep_city}  to  {arr_city}", styles["SegCities"]) if (dep_city or arr_city) else None

    left_col = [
        Paragraph("DEPARTS", styles["LabelSmall"]),
        Paragraph(_s(seg.get("departure_date")) or "-", styles["ValueMed"]),
        Paragraph(_s(seg.get("departure_time")) or "-", styles["ValueMed"]),
    ]
    dep_term = _s(seg.get("departure_terminal"))
    if dep_term:
        left_col.append(Paragraph(f"Terminal {dep_term}", styles["MetaLine"]))

    mid_col = [
        Paragraph("DURATION", styles["LabelSmall"]),
        Paragraph(_s(seg.get("duration")) or "-", styles["ValueMed"]),
        Paragraph(_s(seg.get("cabin_class")) or "", styles["MetaLine"]),
    ]

    right_col = [
        Paragraph("ARRIVES", styles["LabelSmall"]),
        Paragraph(_s(seg.get("arrival_date")) or "-", styles["ValueMed"]),
        Paragraph(_s(seg.get("arrival_time")) or "-", styles["ValueMed"]),
    ]
    arr_term = _s(seg.get("arrival_terminal"))
    if arr_term:
        right_col.append(Paragraph(f"Terminal {arr_term}", styles["MetaLine"]))

    body_grid = Table([[left_col, mid_col, right_col]], colWidths=[53.3 * mm, 53.3 * mm, 53.4 * mm])
    body_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))

    meta_bits = []
    if seg.get("pnr"):
        meta_bits.append(f"PNR {_s(seg['pnr'])}")
    if seg.get("baggage"):
        meta_bits.append(f"Baggage {_s(seg['baggage'])}")
    if seg.get("seat"):
        meta_bits.append(f"Seat {_s(seg['seat'])}")
    meta_line = Paragraph("   •   ".join(meta_bits), styles["MetaLine"]) if meta_bits else None

    # A technical stop is information about THIS flight's own routing (same
    # flight number continues after a brief landing) — it can't be derived
    # from the gap to the next segment, so it comes from the extracted text.
    tech_stop = technical_stop_text(_s(seg.get("stops")))
    tech_note = Paragraph(f"✈ {tech_stop}", styles["TechNote"]) if tech_stop else None

    body_rows = [[seg_header], [Spacer(1, 8)], [route]]
    if cities:
        body_rows.append([cities])
    body_rows += [[Spacer(1, 8)], [body_grid]]
    if tech_note:
        body_rows += [[Spacer(1, 5)], [tech_note]]
    if meta_line:
        body_rows += [[Spacer(1, 6)], [meta_line]]
    else:
        body_rows += [[Spacer(1, 4)]]

    card = Table(body_rows, colWidths=[160 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 1), (-1, -1), CARD_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, NAVY),
        ("LEFTPADDING", (0, 1), (-1, -1), 10),
        ("RIGHTPADDING", (0, 1), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, 0), 0),
        ("RIGHTPADDING", (0, 0), (-1, 0), 0),
    ]))
    return card


def _journey_labels(trip_type: str, journeys: list) -> list:
    """Decides section labels for each journey group based on trip type and
    how many distinct journeys were actually detected. Returns a list the
    same length as `journeys`, or [] if no headers should be shown at all
    (one-way trips, or a single detected journey)."""
    if len(journeys) <= 1:
        return []
    if trip_type == "Round Trip" and len(journeys) == 2:
        return ["Onward Journey", "Return Journey"]
    return [f"Journey {i + 1}" for i in range(len(journeys))]


def generate_itinerary_pdf(output_path: str, passenger_names: list,
                            trip_type: str, segments: list) -> str:
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
    )
    story = []

    story.append(Paragraph("Travel Itinerary", styles["DocTitle"]))
    story.append(Paragraph(trip_type, styles["DocSubtitle"]))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=10))

    if isinstance(passenger_names, str):
        passenger_names = [passenger_names]
    clean_names = [n.strip() for n in passenger_names if n and n.strip()] or ["Passenger"]
    if len(clean_names) == 1:
        story.append(Paragraph(f"Passenger: <b>{clean_names[0]}</b>", styles["PaxLine"]))
    else:
        story.append(Paragraph(f"Passengers ({len(clean_names)}):", styles["PaxLine"]))
        for i, name in enumerate(clean_names, start=1):
            story.append(Paragraph(f"{i}. <b>{name}</b>", styles["PaxLine"]))
    story.append(Spacer(1, 14))

    if not segments:
        story.append(Paragraph("No flight segments were provided.", styles["MetaLine"]))
    else:
        journeys = group_into_journeys(segments)
        labels = _journey_labels(trip_type, journeys)
        total_flights = len(segments)
        flight_index = 0

        for j_idx, journey in enumerate(journeys):
            if labels:
                story.append(_journey_header(labels[j_idx]))
                story.append(Spacer(1, 8))

            for k, seg in enumerate(journey):
                flight_index += 1
                story.append(KeepTogether([_segment_card(seg, flight_index, total_flights), Spacer(1, 10)]))

                if k + 1 < len(journey):
                    transit = transit_between(seg, journey[k + 1])
                    if transit:
                        story.append(KeepTogether([_transit_strip(transit), Spacer(1, 10)]))

            if j_idx + 1 < len(journeys):
                story.append(Spacer(1, 6))

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=TEXT_GREY, spaceAfter=6))
    story.append(Paragraph(
        "This itinerary is for reference only and is subject to airline confirmation.",
        styles["FooterNote"]))

    doc.build(story)
    return output_path


def build_output_filename(passenger_names: list, segments: list) -> str:
    pnr = ""
    for s_ in segments:
        if s_.get("pnr"):
            pnr = s_["pnr"]
            break
    if isinstance(passenger_names, str):
        passenger_names = [passenger_names]
    clean_names = [n.strip() for n in passenger_names if n and n.strip()] or ["Passenger"]
    raw_first = clean_names[0].split(" ")[0] if clean_names[0] else "PASSENGER"
    first_name = re.sub(r"[^A-Za-z0-9]", "", raw_first).upper() or "PASSENGER"
    suffix = f"_PLUS{len(clean_names) - 1}" if len(clean_names) > 1 else ""
    if pnr:
        return f"{pnr}_{first_name}{suffix}.pdf"
    return f"ITINERARY_{first_name}{suffix}.pdf"
