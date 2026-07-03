# Flight Itinerary Builder (WhatsApp output)

Upload flight screenshots (one-way, round trip, or multi-city), extract the
flight details with Groq's vision model, review/edit them, then generate a
short text summary ready to copy or send straight to WhatsApp.

No PDF, no fixed branding — this is a generic internal tool.

## How it works

1. **Upload** — drop 1+ screenshots. Multiple images are supported for
   round-trip (outbound + return) or multi-city (one image per leg, or one
   image containing several legs).
2. **Extract** — each image is sent to Groq's vision model with a strict JSON
   schema prompt (`extract.py`). Segments from all images are merged and
   sorted by date.
3. **Review** — every field is editable in the browser before you commit,
   since vision extraction won't always be perfect (blurry crops, unusual
   airline layouts, etc).
4. **Generate** — `text_gen.py` builds a short WhatsApp-formatted message
   (using WhatsApp's own `*bold*` / `_italic_` syntax) with one block per
   flight leg. You can copy the text or tap "Open in WhatsApp", which opens
   `wa.me` with the message pre-filled so you just pick the contact and send.

## Local setup

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in GROQ_API_KEY
python app.py
```

Visit http://localhost:5000

## Deploying to Railway

1. Push this folder to a new GitHub repo.
2. In Railway: New Project → Deploy from GitHub repo.
3. Add environment variables from `.env.example` (at minimum `GROQ_API_KEY`).
4. Railway will detect the `Procfile` and run `gunicorn app:app` automatically.

## Notes on the Groq vision model

Groq's model lineup changes often — `llama-4-scout` was deprecated on
**17 June 2026**. This app currently defaults to `qwen/qwen3.6-27b` via the
`GROQ_VISION_MODEL` env var, but it's a preview model. Before relying on
this in production, check https://console.groq.com/docs/vision for the
current recommended vision-capable model and update the env var if needed —
no code change required.

## Known limitations / next steps

- No auth yet — anyone with the URL can use it. Add basic auth or a login if
  this goes on a public Railway URL.
- Extraction quality depends on screenshot clarity — cropped/zoomed
  screenshots of just the flight card (not the whole browser window) work
  best.
- `wa.me/?text=...` (no phone number) opens WhatsApp and lets you pick the
  contact yourself. If you want it to jump straight to a known number, build
  the link as `https://wa.me/<countrycode><number>?text=...` instead — easy
  tweak in `static/app.js`.
- Uploaded images are deleted from the server right after extraction;
  nothing is persisted.
