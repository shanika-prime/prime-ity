"""
Image preprocessing before sending to the vision model.

This mirrors the approach from Prime Ticket (a sibling project with proven
good extraction accuracy): downscale large images to a reasonable max
dimension and moderately compress as JPEG, rather than upscaling and
sending lossless PNGs. In practice, oversized/lossless payloads seem to
hurt more than help — likely due to how the vision model internally
tiles/downsamples large images, plus larger payloads mean more latency and
more chances for truncation. Keep it simple and match what's proven to work.
"""
import io
import base64
import logging
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

MAX_DIM = 1600
JPEG_QUALITY = 82
# Genuinely tiny screenshots (e.g. a cropped phone screenshot saved small)
# get a mild upscale so text isn't microscopic - but this is the exception,
# not the primary behavior.
MIN_DIM_FOR_UPSCALE = 700
UPSCALE_TARGET = 1000


def preprocess_image_to_data_url(image_path: str) -> str:
    """Loads, normalizes, and re-encodes an image, returning a base64 data
    URL. Falls back to the raw file bytes if anything in the pipeline
    fails — a failed enhancement should never block extraction entirely."""
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)  # respect phone photo rotation
        img = img.convert("RGB")  # drop alpha, normalize mode

        w, h = img.size
        if max(w, h) > MAX_DIM:
            scale = MAX_DIM / max(w, h)
            img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        elif max(w, h) < MIN_DIM_FOR_UPSCALE:
            scale = UPSCALE_TARGET / max(w, h)
            img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        logger.exception("Image preprocessing failed for %s; sending raw file", image_path)
        import os
        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        mime = "jpeg" if ext in ("jpg", "jpeg") else (ext or "png")
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/{mime};base64,{b64}"
