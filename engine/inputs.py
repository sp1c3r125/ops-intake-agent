"""Load inputs: .eml, .txt, .png/.jpg, .pdf, CSV rows. Everything loaded here is untrusted.

An unreadable file does not stop the run: it becomes an Item with a `preset_reason`, and the pipeline sends
it to a person without calling Claude.
"""
from __future__ import annotations

import csv
import email
import html
import io
import re
from dataclasses import dataclass
from email import policy
from pathlib import Path

from . import ocr

MAX_DOC_CHARS = 20000   # cap on text sent to the model per item
MAX_PDF_PAGES_AS_IMAGE = 3
KINDS = ("email", "text", "image", "pdf", "csv_rows")
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@dataclass
class Item:
    id: str
    text: str = ""
    image: tuple | None = None        # (bytes, mime) when IMAGE_MODE=vision
    row: dict | None = None           # the CSV row, for csv_rows
    path: Path | None = None
    preset_reason: str | None = None  # send to a person without calling Claude
    note: str | None = None           # detail for the log


def neutralise(text):
    """Stop untrusted text from closing or opening our <document> tag."""
    return re.sub(r"(?i)<\s*(/?)\s*document", r"&lt;\1document", text)


def document_text(item):
    """The user message for the model: the untrusted content inside <document> tags."""
    body = item.text if item.image is None else "(The document is the attached image.)"
    return f"<document>\n{neutralise(body)}\n</document>"


def _clip(text):
    text = text.strip()
    return text if len(text) <= MAX_DOC_CHARS else text[:MAX_DOC_CHARS] + "\n[truncated]"


# --------------------------------------------------------------------------- PDF
def pdf_pages(source):
    """Page texts of a PDF (a path or bytes). Raises on an unreadable file."""
    import pdfplumber
    src = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    with pdfplumber.open(src) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


def _pdf_page_images(source):
    """Render the first few pages and stack them into one PNG. Returns PNG bytes."""
    import pdfplumber
    from PIL import Image
    src = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    with pdfplumber.open(src) as pdf:
        pages = [p.to_image(resolution=150).original.convert("RGB") for p in pdf.pages[:MAX_PDF_PAGES_AS_IMAGE]]
    if not pages:
        raise ValueError("no pages")
    width = max(p.width for p in pages)
    sheet = Image.new("RGB", (width, sum(p.height for p in pages)), "white")
    y = 0
    for p in pages:
        sheet.paste(p, (0, y))
        y += p.height
    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()


def _from_image_bytes(item, data, mime, image_mode):
    """Fill an Item from image bytes using the IMAGE_MODE path. Sets preset_reason if that path fails."""
    if image_mode == "vision":
        item.image = (data, mime)
        return item
    if not ocr.available():
        item.preset_reason = "ocr_unavailable"
        item.note = "IMAGE_MODE=tesseract but Tesseract is not installed"
        return item
    try:
        item.text = _clip(ocr.image_to_text(data))
    except ocr.OcrError as e:
        item.preset_reason, item.note = "ocr_unavailable", str(e)[:200]
    return item


def _load_pdf(path, image_mode):
    item = Item(id=path.name, path=path)
    try:
        pages = pdf_pages(path)
    except Exception as e:
        item.preset_reason, item.note = "unreadable_input", f"PDF unreadable: {e}"[:200]
        return item
    text = "\n".join(pages).strip()
    if text:
        item.text = _clip(text)
        return item
    # No text layer: use the IMAGE_MODE path (SPEC "Backends and images").
    try:
        png = _pdf_page_images(path)
    except Exception as e:
        item.preset_reason, item.note = "no_text_layer", f"could not render the PDF: {e}"[:200]
        return item
    _from_image_bytes(item, png, "image/png", image_mode)
    if item.preset_reason:                       # image path not available
        item.preset_reason = "no_text_layer"
    elif not item.image and not item.text.strip():  # OCR found nothing
        item.preset_reason, item.note = "no_text_layer", "OCR found no text"
    return item


# --------------------------------------------------------------------------- email
def _plain_body(msg):
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_type() == "text/html":
        content = html.unescape(re.sub(r"<[^>]+>", " ", content))
        content = re.sub(r"[ \t]+", " ", content)
    return content


def _load_email(path):
    item = Item(id=path.name, path=path)
    try:
        with path.open("rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        attachments = list(msg.iter_attachments())
        names = [a.get_filename() or "(unnamed)" for a in attachments]
        parts = [f"From: {msg['From']}", f"To: {msg['To']}", f"Date: {msg['Date']}",
                 f"Subject: {msg['Subject']}", f"Attachments: {', '.join(names) or 'none'}", "",
                 _plain_body(msg).strip()]
        for a, name in zip(attachments, names):
            if a.get_content_type() == "application/pdf" or name.lower().endswith(".pdf"):
                try:
                    text = "\n".join(pdf_pages(a.get_content())).strip()
                except Exception:
                    text = ""
                parts += ["", f"--- Attachment {name} (text) ---",
                          text or "(no text could be read from this PDF)"]
        item.text = _clip("\n".join(parts))
    except Exception as e:
        item.preset_reason, item.note = "unreadable_input", f"email unreadable: {e}"[:200]
    return item


# --------------------------------------------------------------------------- loader
def _load_csv_rows(path):
    items = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for n, row in enumerate(csv.DictReader(f), start=1):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            first = next(iter(row.values()), "")
            text = "\n".join(f"{k}: {v}" for k, v in row.items())
            items.append(Item(id=first or f"row-{n}", text=_clip(text), row=row, path=path))
    return items


def load_items(kind, pack_dir, glob, image_mode):
    """All items for a pack, in sorted (repeatable) order."""
    if kind not in KINDS:
        raise ValueError(f"INPUT_KIND must be one of {KINDS}, not {kind!r}")
    items = []
    for path in sorted(Path(pack_dir).glob(glob)):
        if kind == "csv_rows":
            items += _load_csv_rows(path)
        elif kind == "email":
            items.append(_load_email(path))
        elif kind == "text":
            items.append(Item(id=path.name, path=path,
                              text=_clip(path.read_text(encoding="utf-8", errors="replace"))))
        elif kind == "pdf":
            items.append(_load_pdf(path, image_mode))
        else:  # image
            item = Item(id=path.name, path=path)
            mime = IMAGE_MIME.get(path.suffix.lower())
            if mime is None:
                item.preset_reason, item.note = "unreadable_input", f"unsupported image type {path.suffix}"
            else:
                item = _from_image_bytes(item, path.read_bytes(), mime, image_mode)
            items.append(item)
    return items
