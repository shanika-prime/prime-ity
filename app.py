import os
import uuid
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

from extract import extract_segments_from_images
from text_gen import build_whatsapp_message

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB total upload cap

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "tmp_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    trip_type = request.form.get("trip_type", "One Way")
    files = request.files.getlist("images")

    if not files:
        return jsonify({"error": "No images uploaded."}), 400

    session_id = uuid.uuid4().hex[:12]
    saved_paths = []
    try:
        for f in files:
            if f and _allowed(f.filename):
                fname = f"{session_id}_{secure_filename(f.filename)}"
                path = os.path.join(UPLOAD_DIR, fname)
                f.save(path)
                saved_paths.append(path)

        if not saved_paths:
            return jsonify({"error": "No valid image files (png/jpg/webp) found."}), 400

        segments = extract_segments_from_images(saved_paths)
        return jsonify({"trip_type": trip_type, "segments": segments})
    finally:
        for p in saved_paths:
            try:
                os.remove(p)
            except OSError:
                pass


@app.route("/generate-text", methods=["POST"])
def generate_text():
    data = request.get_json(force=True)
    passenger_name = (data.get("passenger_name") or "").strip()
    trip_type = data.get("trip_type", "One Way")
    segments = data.get("segments", [])

    if not passenger_name:
        return jsonify({"error": "Passenger name is required."}), 400
    if not segments:
        return jsonify({"error": "No flight segments to build a message from."}), 400

    message = build_whatsapp_message(passenger_name, trip_type, segments)
    return jsonify({"message": message})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
