"""
Extraction of structured flight-segment data from itinerary screenshots and
booking-document text, using Groq's vision-capable model.

This mirrors the approach used by Prime Ticket (a sibling project with
proven good extraction accuracy) rather than assumptions from generic
vendor docs:
- Single model call per file, no "thinking"/reasoning mode
  (reasoning_effort="none") and no second verification pass. In practice,
  thinking mode gives the model room to paraphrase instead of transcribing
  literally, which hurts this kind of read-exactly-what's-there extraction.
- When multiple images or PDFs are uploaded together, each one gets its own
  dedicated extraction call rather than being combined into one request —
  batching multiple files into a single call was tried and found to reduce
  accuracy (the model can conflate details across files when several are in
  one prompt at once). One call per file, merged afterward, is simpler and
  matches what's proven most accurate in practice across every tab.
- Images are downscaled to a moderate size and JPEG-compressed rather than
  upscaled/sent as lossless PNGs — oversized payloads seem to hurt more
  than help.
- The prompt includes a concrete worked example and explicit keyword rules
  for telling a technical stop apart from a layover/transfer, instead of
  abstract "be careful" instructions.

Post-extraction, every field still goes through validate.py for format
normalization — that safety net stays regardless of extraction quality.

Groq's model lineup changes frequently (see console.groq.com/docs/deprecations).
The model id is read from GROQ_VISION_MODEL so it can be swapped without a
code change if the current preview model is retired.
"""
import os
import re
import json
import logging
import groq
from groq import Groq

from preprocess import preprocess_image_to_data_url
from validate import validate_segments

logger = logging.getLogger(__name__)

VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

# Created lazily on first use (not at import) so a missing GROQ_API_KEY
# logs a clear error at request time instead of crashing the app on boot.
_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY is not set")
            return None
        _client = Groq(api_key=api_key)
    return _client


EXTRACT_PROMPT = """You are a flight data extractor. Return ONLY a raw JSON object — no markdown, no prose.

Structure:
{
  "segments": [
    {
      "airline": "Full airline name",
      "flight_number": "XX 123",
      "cabin_class": "Economy/Business/First",
      "departure_airport_code": "3-letter IATA code",
      "departure_city": "City",
      "departure_date": "YYYY-MM-DD only if the YEAR is actually visible in the source",
      "departure_time": "24hr HH:MM",
      "departure_terminal": "",
      "arrival_airport_code": "3-letter IATA code",
      "arrival_city": "City",
      "arrival_date": "YYYY-MM-DD only if the YEAR is actually visible in the source",
      "arrival_time": "24hr HH:MM",
      "arrival_terminal": "",
      "duration": "e.g. 4h 25m",
      "stops": "",
      "baggage": "",
      "pnr": "",
      "seat": ""
    }
  ]
}

One flight segment = one flight number. If a connecting itinerary shows
several flight numbers toward the same final destination, list each as its
own segment object, in chronological order.

STOPS FIELD — read carefully, this is the field most often gotten wrong.
Two different things can appear here, and they are NOT the same:

- STOPOVER = a brief technical stop WITHIN one flight — the SAME flight
  number continues afterward. Look for: "Stop", "Technical stop", "via".
  Write it on that flight's own "stops" field as:
  "Technical stop at CODE - duration" (e.g. "Technical stop at MLE - 1hr")

- TRANSIT = a layover BETWEEN two DIFFERENT flight numbers at the same
  airport, before boarding the next flight. Look for: "Transfer",
  "Layover", "Connecting". Write it on the FIRST of the two flights'
  "stops" field as:
  "Layover at CODE - duration" (e.g. "Layover at DOH - 3h 15m")

A flight can have neither, either, or (rarely) both — check independently.
If there is no stop of either kind, use "Non-stop". Never guess a duration
you can't see; if the source doesn't show it, omit the "- duration" part.

Worked example — source describes: CMB to DOH on GF145 with a technical
stop at Male (MLE) for 1hr, then a 3h15m layover at Doha before boarding
GF181 to JED:

{"segments": [
  {"airline": "Gulf Air", "flight_number": "GF 145",
   "departure_airport_code": "CMB", "arrival_airport_code": "DOH",
   "stops": "Technical stop at MLE - 1hr; Layover at DOH - 3h 15m", ...},
  {"airline": "Gulf Air", "flight_number": "GF 181",
   "departure_airport_code": "DOH", "arrival_airport_code": "JED",
   "stops": "Non-stop", ...}
]}

Other rules:
- If a field is not present in the source, use "" — never guess.
- Airport codes must be the 3-letter IATA code if shown (e.g. CMB, DXB).
- Times in 24hr HH:MM.

YEAR — do not guess this under any circumstances. Only include a year in
departure_date/arrival_date if you can actually see it written in the
source. If the day and month are shown but no year is visible, write just
"DD Mon" (e.g. "14 Aug") with NO year attached — do not fill in a year
from assumption, habit, or any other source. A wrong year is worse than no
year at all.

ITINERARY SOURCE:
"""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _parse_segments_response(raw: str, context: str) -> list:
    """Parses the model's JSON response into a raw segment list. Tolerates
    stray prose around the JSON (fallback regex extraction of the first
    {...} block). Never raises — logs and returns [] on any failure."""
    if not raw or not raw.strip():
        logger.warning("Empty model response for %s", context)
        return []

    cleaned = _strip_json_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            logger.warning("Could not parse JSON from Groq response for %s: %r", context, raw)
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from Groq response for %s: %r", context, raw)
            return []

    segments = parsed.get("segments", []) if isinstance(parsed, dict) else []
    if isinstance(segments, dict):
        segments = [segments]
    return segments if isinstance(segments, list) else []


def _chat(content, context: str) -> str:
    """Single Groq call — no thinking mode, no verification pass, no
    batching of multiple files into one call. Returns raw response text,
    or '' on any API failure (logged, never raised)."""
    client = _get_client()
    if client is None:
        return ""
    try:
        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            max_completion_tokens=4000,
            response_format={"type": "json_object"},
            reasoning_effort="none",  # skip "thinking" tokens - we want fast, deterministic, literal extraction
        )
        return completion.choices[0].message.content or ""
    except groq.RateLimitError as e:
        logger.warning("Groq rate limit hit for %s: %s", context, e)
        return ""
    except groq.APIStatusError as e:
        logger.warning("Groq API error for %s: HTTP %s %s", context, e.status_code, e)
        return ""
    except Exception:
        logger.exception("Groq call failed for %s", context)
        return ""


def _sort_segments(segments: list) -> list:
    def sort_key(seg):
        return (seg.get("departure_date") or "9999", seg.get("departure_time") or "99:99")
    segments.sort(key=sort_key)
    return segments


# --- Image-based extraction -------------------------------------------------

def extract_segments_from_image(image_path: str) -> list:
    """Single-image extraction. Used when a file needs to be processed on
    its own (e.g. the WhatsApp tab's onward/return round-trip split, where
    each uploaded file is a separate journey)."""
    data_url = preprocess_image_to_data_url(image_path)
    content = [
        {"type": "text", "text": EXTRACT_PROMPT +
         "\n(The itinerary details are in the attached image below. Respond with "
         "ONLY the JSON object.)"},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    raw = _chat(content, image_path)
    return validate_segments(_parse_segments_response(raw, image_path))


def extract_segments_from_images(image_paths: list) -> list:
    """Multi-image extraction: one dedicated call per image, then merge and
    sort. This matches the WhatsApp tab's approach exactly (which has
    proven the most accurate in practice) — batching multiple images into
    a single call was tried and found to reduce accuracy, likely because
    the model can conflate details across images when several are in one
    prompt. Simpler, and consistent across every tab in the app."""
    if not image_paths:
        return []
    all_segments = []
    for path in image_paths:
        all_segments.extend(extract_segments_from_image(path))
    return _sort_segments(all_segments)


# --- Text-based extraction (PDF documents) ----------------------------------

def extract_segments_from_text(text: str, context: str = "pdf") -> list:
    """Single-document text extraction. Used when a file needs to be
    processed on its own (e.g. the WhatsApp tab's round-trip split)."""
    if not text or not text.strip():
        return []
    content = [{"type": "text", "text": EXTRACT_PROMPT + text}]
    raw = _chat(content, context)
    return validate_segments(_parse_segments_response(raw, context))


def extract_segments_from_pdf_texts(texts: list) -> list:
    """Multi-PDF extraction: one dedicated call per document, then merge
    and sort — same reasoning as extract_segments_from_images."""
    non_empty = [t for t in texts if t and t.strip()]
    if not non_empty:
        return []
    all_segments = []
    for i, text in enumerate(non_empty):
        all_segments.extend(extract_segments_from_text(text, context=f"pdf[{i}]"))
    return _sort_segments(all_segments)
