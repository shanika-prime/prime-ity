import os
import time
import uuid
from flask import Flask, request, jsonify, render_template, send_file, after_this_request
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

from extract import extract_segments_from_images, extract_segments_from_pdf_texts
from extract_pdf import extract_text_from_pdf
from text_gen import build_whatsapp_message
from pdf_gen import generate_itinerary_pdf, build_output_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB total upload cap

# Bumps once per process start (i.e. every deploy/restart), used as a
# cache-busting query string on static assets so phones/browsers don't keep
# serving a stale app.js or style.css after we ship a fix.
ASSET_VERSION = str(int(time.time()))


@app.context_processor
def inject_asset_version():
    return {"asset_version": ASSET_VERSION}


UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "tmp_uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "tmp_output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
ALLOWED_PDF_EXT = {"pdf"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _allowed_pdf(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PDF_EXT


@app.errorhandler(413)
def too_large(e):
    mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({"error": f"Upload too large — total size must be under {mb}MB. Try fewer or smaller screenshots."}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Something went wrong on the server. Please try again."}), 500


def _save_uploaded_files(files, allowed_check):
    """Saves valid uploaded files to disk, returns the list of saved paths.
    Caller is responsible for deleting them afterwards."""
    session_id = uuid.uuid4().hex[:12]
    saved_paths = []
    for f in files:
        if f and allowed_check(f.filename):
            fname = f"{session_id}_{secure_filename(f.filename)}"
            path = os.path.join(UPLOAD_DIR, fname)
            f.save(path)
            saved_paths.append(path)
    return saved_paths


def _cleanup(paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """One-click WhatsApp flow: upload -> extract -> message, no review step."""
    trip_type = request.form.get("trip_type", "One Way")
    files = request.files.getlist("images")

    if not files:
        return jsonify({"error": "No images uploaded."}), 400

    saved_paths = _save_uploaded_files(files, _allowed)
    try:
        if not saved_paths:
            return jsonify({"error": "No valid image files (png/jpg/webp) found."}), 400

        segments = extract_segments_from_images(saved_paths)
        if not segments:
            return jsonify({"error": "No flight details could be read from those images. Try clearer screenshots."}), 422

        message = build_whatsapp_message(trip_type, segments)
        return jsonify({"message": message})
    finally:
        _cleanup(saved_paths)


@app.route("/extract", methods=["POST"])
def extract():
    """PDF flow, step 1: upload -> extract -> editable segments for review."""
    trip_type = request.form.get("trip_type", "One Way")
    files = request.files.getlist("images")

    if not files:
        return jsonify({"error": "No images uploaded."}), 400

    saved_paths = _save_uploaded_files(files, _allowed)
    try:
        if not saved_paths:
            return jsonify({"error": "No valid image files (png/jpg/webp) found."}), 400

        segments = extract_segments_from_images(saved_paths)
        if not segments:
            return jsonify({"error": "No flight details could be read from those images. Try clearer screenshots."}), 422

        return jsonify({"trip_type": trip_type, "segments": segments})
    finally:
        _cleanup(saved_paths)


@app.route("/extract-pdf", methods=["POST"])
def extract_pdf():
    """PDF-to-PDF flow: upload booking PDF(s) -> extract text -> Groq text
    extraction -> editable segments for review."""
    trip_type = request.form.get("trip_type", "One Way")
    files = request.files.getlist("pdfs")

    if not files:
        return jsonify({"error": "No PDF files uploaded."}), 400

    saved_paths = _save_uploaded_files(files, _allowed_pdf)
    try:
        if not saved_paths:
            return jsonify({"error": "No valid PDF files found."}), 400

        texts = [extract_text_from_pdf(p) for p in saved_paths]
        if not any(t.strip() for t in texts):
            return jsonify({
                "error": "No readable text found in those PDFs. They may be scanned/image-only — "
                         "try the screenshot upload tabs instead."
            }), 422

        segments = extract_segments_from_pdf_texts(texts)
        if not segments:
            return jsonify({"error": "No flight details could be read from those PDFs."}), 422

        return jsonify({"trip_type": trip_type, "segments": segments})
    finally:
        _cleanup(saved_paths)


@app.route("/generate-pdf", methods=["POST"])
def generate_pdf():
    """PDF flow, step 2: edited segments + passenger name(s) -> itinerary PDF."""
    data = request.get_json(force=True)
    passenger_names = data.get("passenger_names")
    if not isinstance(passenger_names, list):
        # backward-compatible fallback if a single passenger_name string is sent
        single = (data.get("passenger_name") or "").strip()
        passenger_names = [single] if single else []
    passenger_names = [str(n).strip() for n in passenger_names if str(n).strip()] or ["Passenger"]

    trip_type = data.get("trip_type", "One Way")
    segments = data.get("segments", [])

    if not segments:
        return jsonify({"error": "No flight segments to build an itinerary from."}), 400

    out_name = build_output_filename(passenger_names, segments)
    out_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4().hex[:8]}_{out_name}")
    generate_itinerary_pdf(out_path, passenger_names, trip_type, segments)

    @after_this_request
    def _remove_pdf(response):
        try:
            os.remove(out_path)
        except OSError:
            pass
        return response

    return send_file(
        out_path,
        as_attachment=True,
        download_name=out_name,
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
