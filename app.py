import os
import uuid
from flask import Flask, request, jsonify, render_template, send_file, after_this_request
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

from extract import extract_segments_from_images
from text_gen import build_whatsapp_message
from pdf_gen import generate_itinerary_pdf, build_output_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB total upload cap

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "tmp_uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "tmp_output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _save_uploaded_images(files):
    """Saves valid uploaded images to disk, returns the list of saved paths.
    Caller is responsible for deleting them afterwards."""
    session_id = uuid.uuid4().hex[:12]
    saved_paths = []
    for f in files:
        if f and _allowed(f.filename):
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

    saved_paths = _save_uploaded_images(files)
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

    saved_paths = _save_uploaded_images(files)
    try:
        if not saved_paths:
            return jsonify({"error": "No valid image files (png/jpg/webp) found."}), 400

        segments = extract_segments_from_images(saved_paths)
        if not segments:
            return jsonify({"error": "No flight details could be read from those images. Try clearer screenshots."}), 422

        return jsonify({"trip_type": trip_type, "segments": segments})
    finally:
        _cleanup(saved_paths)


@app.route("/generate-pdf", methods=["POST"])
def generate_pdf():
    """PDF flow, step 2: edited segments + passenger name -> itinerary PDF."""
    data = request.get_json(force=True)
    passenger_name = (data.get("passenger_name") or "").strip() or "Passenger"
    trip_type = data.get("trip_type", "One Way")
    segments = data.get("segments", [])

    if not segments:
        return jsonify({"error": "No flight segments to build an itinerary from."}), 400

    out_name = build_output_filename(passenger_name, segments)
    out_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4().hex[:8]}_{out_name}")
    generate_itinerary_pdf(out_path, passenger_name, trip_type, segments)

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
