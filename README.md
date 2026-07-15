# Flight Itinerary Builder

Three tools in one app:
1. **WhatsApp** — upload flight screenshots, get a short WhatsApp-ready message in one click.
2. **Screenshot → PDF** — upload screenshots, review/edit extracted details, generate a travel itinerary PDF (supports multiple passengers).
3. **PDF → PDF** — upload booking/e-ticket PDFs (with selectable text), same review/edit/generate flow.

## How it works

- **Image extraction** (`extract.py`): screenshots go to Groq's vision model with a strict JSON schema prompt.
- **PDF text extraction** (`extract_pdf.py` + `extract.py`): text is pulled from the PDF with `pdfplumber`, then sent to the same Groq model as plain text for structured extraction. PDFs with no selectable text (scanned/image-only) return a clear error asking you to use the screenshot tabs instead.
- **WhatsApp output** (`text_gen.py`): short message using WhatsApp's own `*bold*` formatting, with a dotted divider around real layovers (vs. a plain line for technical stops or non-stop flights).
- **PDF output** (`pdf_gen.py`): clean, unbranded "Travel Itinerary" PDF built with ReportLab — one card per flight, supports multiple passengers, and each card is kept together so it never splits across a page break.

## Local setup

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in GROQ_API_KEY
python app.py
```

Visit http://localhost:5000

## Deploying to Render

### Option A — Blueprint (one click, recommended)

This repo includes `render.yaml`, so Render can set everything up automatically:

1. Push this repo to GitHub.
2. In the Render Dashboard: **New → Blueprint**, connect the repo.
3. Render reads `render.yaml` and creates the web service with the build/start commands already configured.
4. You'll be prompted to fill in `GROQ_API_KEY` (marked `sync: false` in the blueprint, so it's not stored in git). `GROQ_VISION_MODEL` and `SECRET_KEY` are pre-filled/auto-generated.
5. Click **Apply** — first deploy takes a couple of minutes.

### Option B — Manual web service

1. Push this repo to GitHub.
2. **New → Web Service**, connect the repo.
3. Set:
   - **Language:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Under **Environment**, add:
   ```
   GROQ_API_KEY=your_key_here
   GROQ_VISION_MODEL=qwen/qwen3.6-27b
   SECRET_KEY=<any random string>
   ```
5. **Create Web Service** — Render builds and deploys, and gives you a `*.onrender.com` URL with HTTPS included.

Every push to your connected branch auto-deploys after this.

### Free tier note

Render's free tier spins your service down after 15 minutes of inactivity — the next request after that takes ~30–60 seconds to wake up. If that's a problem for day-to-day use, the Starter plan ($7/mo) keeps it always warm.

## Notes on the Groq vision model

Groq's model lineup changes often — `llama-4-scout` was deprecated on **17 June 2026**. This app currently defaults to `qwen/qwen3.6-27b` via the `GROQ_VISION_MODEL` env var, but it's a preview model. Check https://console.groq.com/docs/vision for the current recommended model before relying on this in production — update the env var if needed, no code change required.

## Known limitations / next steps

- No auth yet — anyone with the URL can use it. Add basic auth or a login if this goes on a public URL.
- Extraction quality depends on screenshot/PDF clarity.
- PDF → PDF only works on PDFs with selectable text (no OCR fallback for scanned documents, to avoid a `poppler`/Tesseract system dependency on the hosting build image).
- Uploaded files are deleted from the server right after extraction/generation; nothing is persisted.
