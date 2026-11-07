"""PDF / image text extraction with page provenance.

* Digital PDF pages -> embedded text (PyMuPDF, falling back to pypdf).
* Scanned PDF pages and images (PNG/JPEG/TIFF) -> Tesseract OCR.
Each page records the method used so provenance is always visible.
"""
from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.errors import ValidationFailed

log = logging.getLogger("n2.documents")

try:  # PyMuPDF is the primary engine
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    fitz = None

try:
    from PIL import Image, ImageSequence
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageSequence = None  # type: ignore

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore

SUPPORTED = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


@dataclass
class PageText:
    page: int
    text: str
    method: str  # digital | ocr | ocr_failed | empty
    char_count: int
    ocr_confidence: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def detect_kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise ValidationFailed(f"Unsupported document type '{ext}'. Supported: {', '.join(sorted(SUPPORTED))}")
    return "pdf" if ext == ".pdf" else "image"


def ocr_available() -> bool:
    return pytesseract is not None and shutil.which("tesseract") is not None


def ocr_image(img, lang: str = "eng") -> tuple[str, float | None]:
    """OCR a PIL image, returning (text, mean word confidence 0-100)."""
    if not ocr_available():
        raise RuntimeError("Tesseract OCR is not installed or not on PATH")
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    lines: dict[tuple[int, int, int], list[str]] = {}
    confs: list[float] = []
    for i, word in enumerate(data["text"]):
        if not word or not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        try:
            c = float(data["conf"][i])
            if c >= 0:
                confs.append(c)
        except (TypeError, ValueError):
            pass
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    conf = round(sum(confs) / len(confs), 1) if confs else None
    return text, conf


def render_pdf_page(content: bytes, page_number: int, dpi: int = 150):
    """Render a 1-based PDF page to a PIL image (PyMuPDF, else pdftoppm)."""
    if fitz is not None:
        with fitz.open(stream=content, filetype="pdf") as doc:
            page = doc[page_number - 1]
            pix = page.get_pixmap(dpi=dpi)
            return Image.open(io.BytesIO(pix.tobytes("png")))
    if shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.pdf"
            src.write_bytes(content)
            out = Path(tmp) / "page"
            subprocess.run(["pdftoppm", "-f", str(page_number), "-l", str(page_number), "-r", str(dpi), "-png",
                            "-singlefile", str(src), str(out)], check=True, capture_output=True, timeout=120)
            img = Image.open(out.with_suffix(".png"))
            img.load()
            return img
    raise RuntimeError("No PDF renderer available (install PyMuPDF)")


def _pdf_digital_text(content: bytes) -> list[str]:
    if fitz is not None:
        with fitz.open(stream=content, filetype="pdf") as doc:
            return [p.get_text("text") or "" for p in doc]
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Install PyMuPDF to process PDFs") from e
    reader = PdfReader(io.BytesIO(content))
    return [(p.extract_text() or "") for p in reader.pages]


def pdf_page_count(content: bytes) -> int:
    return len(_pdf_digital_text(content))


def extract_pages(content: bytes, filename: str, *, lang: str = "eng", dpi: int = 200,
                  min_chars: int = 25) -> list[PageText]:
    kind = detect_kind(filename)
    pages: list[PageText] = []
    if kind == "pdf":
        try:
            texts = _pdf_digital_text(content)
        except Exception as e:  # noqa: BLE001
            raise ValidationFailed(f"Could not open PDF: {e}") from e
        if not texts:
            raise ValidationFailed("PDF contains no pages")
        for i, text in enumerate(texts, start=1):
            if len(text.strip()) >= min_chars:
                pages.append(PageText(i, text.strip(), "digital", len(text.strip())))
                continue
            try:
                img = render_pdf_page(content, i, dpi=dpi)
                ocr_text, conf = ocr_image(img, lang)
                method = "ocr" if ocr_text.strip() else "empty"
                pages.append(PageText(i, ocr_text, method, len(ocr_text), conf))
            except Exception as e:  # noqa: BLE001
                log.warning("OCR failed on page %d: %s", i, e)
                pages.append(PageText(i, text.strip(), "ocr_failed", len(text.strip()), error=str(e)[:300]))
    else:
        if Image is None:
            raise ValidationFailed("Pillow is required for image documents")
        try:
            img = Image.open(io.BytesIO(content))
        except Exception as e:  # noqa: BLE001
            raise ValidationFailed(f"Could not open image: {e}") from e
        frames = [f.copy() for f in ImageSequence.Iterator(img)]
        for i, frame in enumerate(frames, start=1):
            try:
                ocr_text, conf = ocr_image(frame, lang)
                pages.append(PageText(i, ocr_text, "ocr" if ocr_text.strip() else "empty", len(ocr_text), conf))
            except Exception as e:  # noqa: BLE001
                pages.append(PageText(i, "", "ocr_failed", 0, error=str(e)[:300]))
    return pages


def render_page_png(content: bytes, filename: str, page_number: int, dpi: int = 110) -> bytes:
    kind = detect_kind(filename)
    if kind == "pdf":
        img = render_pdf_page(content, page_number, dpi=dpi)
    else:
        src = Image.open(io.BytesIO(content))
        frames = list(ImageSequence.Iterator(src))
        if page_number < 1 or page_number > len(frames):
            raise ValidationFailed("page out of range")
        img = frames[page_number - 1].copy()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
