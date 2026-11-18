"""Optional Tesseract OCR, used when IMAGE_MODE=tesseract. pytesseract is imported lazily so the rest of
the engine works without Tesseract installed."""
from __future__ import annotations

import io


class OcrError(Exception):
    """Tesseract is missing or could not read the image."""


def available():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # not installed, not on PATH, or pytesseract missing
        return False


def image_to_text(data):
    """OCR PNG/JPEG bytes into text. Raises OcrError."""
    try:
        import pytesseract
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            return pytesseract.image_to_string(img)
    except Exception as e:
        raise OcrError(f"OCR failed: {e}") from e
