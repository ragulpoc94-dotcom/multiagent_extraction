import asyncio

import pytest

from app.agents import document_agent
from app.core.errors import ValidationFailed
from app.services import document_service as ds


def test_digital_pdf_keeps_pages(digital_pdf):
    pages = ds.extract_pages(digital_pdf, "doc.pdf")
    assert [p.page for p in pages] == [1, 2]
    assert all(p.method == "digital" for p in pages)
    assert "Asha Verma" in pages[0].text and "Pune Central" in pages[1].text


@pytest.mark.skipif(not ds.ocr_available(), reason="tesseract not installed")
def test_png_uses_ocr(scanned_png):
    pages = ds.extract_pages(scanned_png, "scan.png")
    assert len(pages) == 1 and pages[0].method == "ocr"
    assert "Asha" in pages[0].text
    assert pages[0].ocr_confidence is not None


@pytest.mark.skipif(not ds.ocr_available(), reason="tesseract not installed")
def test_scanned_pdf_page_falls_back_to_ocr(scanned_png):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.open(io.BytesIO(scanned_png)).save(buf, format="PDF")
    pages = ds.extract_pages(buf.getvalue(), "scan.pdf")
    assert pages[0].method == "ocr" and "Verma" in pages[0].text


def test_ocr_failure_is_recorded(monkeypatch, scanned_png):
    def boom(*a, **k):
        raise RuntimeError("tesseract missing")
    monkeypatch.setattr(ds, "ocr_image", boom)
    pages = ds.extract_pages(scanned_png, "scan.png")
    assert pages[0].method == "ocr_failed" and "tesseract" in pages[0].error


def test_unsupported_extension():
    with pytest.raises(ValidationFailed):
        ds.detect_kind("file.docx")


def test_page_render_png(digital_pdf):
    png = ds.render_page_png(digital_pdf, "d.pdf", 1)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_chunking_respects_budget_and_provenance():
    pages = [{"page": i, "text": "x" * 3000} for i in range(1, 5)]
    chunks = document_agent.chunk_pages(pages, budget_tokens=1000)  # ~4000 chars
    assert len(chunks) == 4
    assert all("=== PAGE" in c["text"] for c in chunks)
    big = document_agent.chunk_pages([{"page": 1, "text": "y" * 10000}], budget_tokens=1000)
    assert len(big) == 3 and all(c["pages"] == [1] for c in big) and "part 1/3" in big[0]["text"]
    one = document_agent.chunk_pages(pages, budget_tokens=100000)
    assert len(one) == 1 and one[0]["pages"] == [1, 2, 3, 4]


def test_process_document_once(repo, settings, digital_pdf):
    rec = document_agent.save_upload(repo, settings, digital_pdf, "statement.pdf")
    out = asyncio.run(document_agent.process(repo, settings, rec["id"]))
    assert out["status"] == "processed" and out["page_count"] == 2 and out["methods"] == ["digital"]
    assert out["chunks_planned"] == 1
