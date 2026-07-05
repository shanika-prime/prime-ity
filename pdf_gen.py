"""
Builds a clean, unbranded travel itinerary PDF from merged flight segments
and a passenger name, using ReportLab.
"""
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

NAVY = colors.HexColor("#10233F")
NAVY_DEEP = colors.HexColor("#0A1830")
AMBER = colors.HexColor("#FFB020")
AMBER_DEEP = colors.HexColor("#C7860A")
CARD_BG = colors.HexColor("#EEF1F5")
TEXT_GREY = colors.HexColor("#5B6472")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="DocTitle", fontSize=20, leading=24,
                           textColor=NAVY, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="DocSubtitle", fontSize=12, leading=15,
                           textColor=TEXT_GREY, fontName="Helvetica"))
styles.add(ParagraphStyle(name="PaxLine", fontSize=11, leading=15,
                           textColor=colors.black))
styles.add(ParagraphStyle(name="FlightTag", fontSize=9.5, leading=12,
                           textColor=AMBER, fontName="Helvetica-Bold"))
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
styles.add(ParagraphStyle(name="FooterNote", fontSize=8, leading=10,
                           textColor=TEXT_GREY))


def _s(value) -> str:
    """Coerces any value to a plain string. The model is asked to return
    strings for every field, but isn't 100% reliable — if it ever returns a
    number, list, or nested object instead, this stops that from crashing
    ReportLab's Paragraph() (which requires a str) or string formatting."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _segment_card(seg: dict, index: int, total: int) -> Table:
    dep_code = _s(seg.get("departure_airport_code")) or "---"
    arr_code = _s(seg.get("arrival_airport_code")) or "---"
    dep_city = _s(seg.get("departure_city"))
    arr_city = _s(seg.get("arrival_city"))
    airline = _s(seg.get("airline"))
    flight_no = _s(seg.get("flight_number"))

    tag_text = f"FLIGHT {index} OF {total}" if total > 1 else "FLIGHT"
    seg_header = Table(
        [[Paragraph(tag_text, styles["FlightTag"]),
          Paragraph((f"{airline}  {flight_no}").strip(), styles["SegHeader"])]],
        colWidths=[45 * mm, 115 * mm],
    )
    seg_header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    route = Paragraph(f"{dep_code}  →  {arr_code}", styles["SegRoute"])
    cities = Paragraph(f"{dep_city}  to  {arr_city}", styles["SegCities"])

    left_col = [
        Paragraph("DEPARTS", styles["LabelSmall"]),
        Paragraph(_s(seg.get("departure_date")) or "-", styles["ValueMed"]),
        Paragraph(_s(seg.get("departure_time")) or "-", styles["ValueMed"]),
        Paragraph(f"Terminal {_s(seg.get('departure_terminal')) or '-'}", styles["MetaLine"]),
    ]
    mid_col = [
        Paragraph("DURATION", styles["LabelSmall"]),
        Paragraph(_s(seg.get("duration")) or "-", styles["ValueMed"]),
        Paragraph(_s(seg.get("stops")) or "Non-stop", styles["MetaLine"]),
        Paragraph(_s(seg.get("cabin_class")) or "-", styles["MetaLine"]),
    ]
    right_col = [
        Paragraph("ARRIVES", styles["LabelSmall"]),
        Paragraph(_s(seg.get("arrival_date")) or "-", styles["ValueMed"]),
        Paragraph(_s(seg.get("arrival_time")) or "-", styles["ValueMed"]),
        Paragraph(f"Terminal {_s(seg.get('arrival_terminal')) or '-'}", styles["MetaLine"]),
    ]

    body_grid = Table(
        [[left_col, mid_col, right_col]],
        colWidths=[53.3 * mm, 53.3 * mm, 53.4 * mm],
    )
    body_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))

    meta_bits = []
    if seg.get("pnr"):
        meta_bits.append(f"PNR {seg['pnr']}")
    if seg.get("baggage"):
        meta_bits.append(f"Baggage {seg['baggage']}")
    if seg.get("seat"):
        meta_bits.append(f"Seat {seg['seat']}")
    meta_line = Paragraph("   •   ".join(meta_bits), styles["MetaLine"]) if meta_bits else Spacer(1, 0)

    card = Table(
        [[seg_header],
         [Spacer(1, 8)],
         [route],
         [cities],
         [Spacer(1, 8)],
         [body_grid],
         [Spacer(1, 6)],
         [meta_line]],
        colWidths=[160 * mm],
    )
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
        total = len(segments)
        for i, seg in enumerate(segments, start=1):
            story.append(_segment_card(seg, i, total))
            story.append(Spacer(1, 12))

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=TEXT_GREY, spaceAfter=6))
    story.append(Paragraph(
        "This itinerary is for reference only and is subject to airline confirmation.",
        styles["FooterNote"]))

    doc.build(story)
    return output_path


def build_output_filename(passenger_names: list, segments: list) -> str:
    pnr = ""
    for s in segments:
        if s.get("pnr"):
            pnr = s["pnr"]
            break
    clean_names = [n.strip() for n in passenger_names if n and n.strip()] or ["Passenger"]
    raw_first = clean_names[0].split(" ")[0] if clean_names[0] else "PASSENGER"
    first_name = re.sub(r"[^A-Za-z0-9]", "", raw_first).upper() or "PASSENGER"
    suffix = f"_PLUS{len(clean_names) - 1}" if len(clean_names) > 1 else ""
    if pnr:
        return f"{pnr}_{first_name}{suffix}.pdf"
    return f"ITINERARY_{first_name}{suffix}.pdf"
