"""
Extracts text from uploaded PDF documents (e-tickets, booking confirmations)
so it can be handed to the Groq text model for structured extraction.
"""
import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts all text from a PDF using pdfplumber. Returns '' if no text
    layer is found (e.g. a scanned/image-only PDF with no selectable text)."""
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text.strip())
    except Exception:
        return ""
    return "\n\n".join(text_parts).strip()
