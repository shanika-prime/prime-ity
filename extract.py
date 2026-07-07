"""
Extracts structured flight-segment data from itinerary screenshots using
Groq's vision-capable model.

Groq's model lineup changes frequently (see console.groq.com/docs/deprecations).
The model id is read from GROQ_VISION_MODEL so it can be swapped without a
code change if the current preview model is retired.
"""
import os
import re
import json
import base64
import logging
from groq import Groq

logger = logging.getLogger(__name__)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

SEGMENT_SCHEMA_HINT = """
Return ONLY a JSON object with this exact shape, no markdown fences, no commentary:

{
  "segments": [
    {
      "airline": "",
      "flight_number": "",
      "cabin_class": "",
      "departure_airport_code": "",
      "departure_city": "",
      "departure_date": "",          // format: YYYY-MM-DD if determinable, else as shown
      "departure_time": "",          // e.g. "14:35"
      "departure_terminal": "",
      "arrival_airport_code": "",
      "arrival_city": "",
      "arrival_date": "",
      "arrival_time": "",
      "arrival_terminal": "",
      "duration": "",
      "stops": "",                   // copy the exact wording from the source, e.g. "Non-stop", "1 stop via CMB", "Layover in Dubai - 3h 45m", or "Technical stop in Male" - do NOT paraphrase into a different format, keep words like "Layover" or "Technical stop" verbatim if that's what the source says
      "baggage": "",
      "pnr": "",
      "seat": ""
    }
  ]
}

Rules:
- One source may contain multiple flight segments (e.g. a round trip or a
  multi-city itinerary, or a connecting flight shown as two legs). List each
  leg as its own object in "segments", in chronological order.
- If a field is not present in the source, use an empty string "" - never guess.
- Airport codes should be the 3-letter IATA code if shown (e.g. CMB, DXB).
- Do not include any text outside the JSON object.
"""


def _image_to_data_url(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _parse_segments_response(raw: str, context: str) -> list:
    """Shared JSON-parsing logic for both the vision and text extraction
    paths — never raises, logs and returns [] on any parse failure."""
    cleaned = _strip_json_fences(raw)
    try:
        parsed = json.loads(cleaned)
        segments = parsed.get("segments", [])
        if isinstance(segments, dict):
            segments = [segments]
        return segments
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Could not parse JSON from Groq response for %s: %r", context, raw)
        return []


def extract_segments_from_image(image_path: str) -> list:
    """Sends one image to the Groq vision model and returns a list of
    segment dicts (empty list on any failure — logged, never raised, so one
    bad image/API hiccup doesn't crash the whole request)."""
    try:
        data_url = _image_to_data_url(image_path)

        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SEGMENT_SCHEMA_HINT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=0.1,
            max_completion_tokens=2048,
            response_format={"type": "json_object"},
            reasoning_effort="none",  # skip "thinking" mode - we want fast, deterministic JSON, not reasoning tokens eating the token budget
        )
    except Exception:
        logger.exception("Groq vision extraction failed for %s", image_path)
        return []

    raw = completion.choices[0].message.content
    return _parse_segments_response(raw, image_path)


def extract_segments_from_images(image_paths: list) -> list:
    """Runs extraction across multiple images and returns the combined,
    chronologically-ordered list of segments. Each segment also carries
    a 'source_image' index for traceability/debugging."""
    all_segments = []
    for idx, path in enumerate(image_paths):
        segs = extract_segments_from_image(path)
        for s in segs:
            s["source_image"] = idx
        all_segments.extend(segs)

    def sort_key(seg):
        return (seg.get("departure_date") or "9999", seg.get("departure_time") or "99:99")

    all_segments.sort(key=sort_key)
    return all_segments


def extract_segments_from_text(text: str, context: str = "pdf") -> list:
    """Sends extracted PDF text (e.g. an e-ticket or booking confirmation)
    to the Groq text model and returns a list of segment dicts. Empty list
    on any failure — logged, never raised."""
    if not text.strip():
        return []
    try:
        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are extracting flight itinerary details from the text of a "
                        "ticket/booking confirmation document below.\n\n"
                        + SEGMENT_SCHEMA_HINT
                        + "\n\nDocument text:\n\n"
                        + text
                    ),
                }
            ],
            temperature=0.1,
            max_completion_tokens=2048,
            response_format={"type": "json_object"},
            reasoning_effort="none",
        )
    except Exception:
        logger.exception("Groq text extraction failed for %s", context)
        return []

    raw = completion.choices[0].message.content
    return _parse_segments_response(raw, context)


def extract_segments_from_pdf_texts(texts: list) -> list:
    """Runs extraction across multiple PDFs' extracted text and returns the
    combined, chronologically-ordered list of segments."""
    all_segments = []
    for idx, text in enumerate(texts):
        segs = extract_segments_from_text(text, context=f"pdf[{idx}]")
        for s in segs:
            s["source_pdf"] = idx
        all_segments.extend(segs)

    def sort_key(seg):
        return (seg.get("departure_date") or "9999", seg.get("departure_time") or "99:99")

    all_segments.sort(key=sort_key)
    return all_segments
