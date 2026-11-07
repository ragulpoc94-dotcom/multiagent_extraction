"""Document Processing Agent: process once, reuse for all nine executions."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.core.utils import estimate_tokens, new_id, utcnow
from app.db.repository import Repository
from app.services import document_service


def save_upload(repo: Repository, settings: Settings, content: bytes, filename: str) -> dict[str, Any]:
    kind = document_service.detect_kind(filename)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"File exceeds {settings.max_upload_mb} MB limit")
    if not content:
        raise ValidationFailed("Empty file")
    did = new_id("doc")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    path = settings.upload_dir / f"{did}{Path(safe_name).suffix.lower()}"
    path.write_bytes(content)
    return repo.insert("documents", did, {
        "filename": safe_name,
        "kind": kind,
        "mime": document_service.SUPPORTED[Path(safe_name).suffix.lower()],
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "path": str(path),
        "pages": [],
    }, status="uploaded")


async def process(repo: Repository, settings: Settings, document_id: str) -> dict[str, Any]:
    rec = repo.get("documents", document_id)
    repo.update("documents", document_id, {"status": "processing", "error": None})
    content = Path(rec["path"]).read_bytes()
    started = utcnow()
    try:
        pages = await asyncio.to_thread(
            document_service.extract_pages, content, rec["filename"], lang=settings.ocr_language,
            dpi=settings.ocr_dpi, min_chars=settings.min_chars_for_digital_page)
    except ValidationFailed as e:
        repo.update("documents", document_id, {"status": "failed", "error": e.message})
        raise
    except Exception as e:  # noqa: BLE001
        repo.update("documents", document_id, {"status": "failed", "error": str(e)[:500]})
        raise ValidationFailed(f"Document processing failed: {e}") from e
    page_dicts = [p.to_dict() for p in pages]
    methods = sorted({p.method for p in pages})
    total_chars = sum(p.char_count for p in pages)
    full = build_document_text(page_dicts)
    status = "processed" if total_chars > 0 else "failed"
    return repo.update("documents", document_id, {
        "status": status,
        "pages": page_dicts,
        "page_count": len(pages),
        "methods": methods,
        "total_chars": total_chars,
        "estimated_tokens": estimate_tokens(full),
        "chunks_planned": len(chunk_pages(page_dicts, settings.max_document_tokens)),
        "ocr_available": document_service.ocr_available(),
        "processing_started_at": started,
        "processed_at": utcnow(),
        "error": None if total_chars else "No text could be extracted from the document",
    })


def page_block(page: dict[str, Any]) -> str:
    return f"=== PAGE {page['page']} ===\n{page.get('text') or ''}".rstrip()


def build_document_text(pages: list[dict[str, Any]]) -> str:
    return "\n\n".join(page_block(p) for p in pages)


def chunk_pages(pages: list[dict[str, Any]], budget_tokens: int) -> list[dict[str, Any]]:
    """Split the document into page-aligned chunks that fit the token budget.

    Oversized single pages are split into parts that keep the page marker so
    provenance is preserved. Returns [{"pages": [..], "text": str, "tokens": int}].
    """
    budget_chars = max(100, budget_tokens * 4)
    chunks: list[dict[str, Any]] = []
    cur_text: list[str] = []
    cur_pages: list[int] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur_text, cur_pages, cur_len
        if cur_text:
            text = "\n\n".join(cur_text)
            chunks.append({"pages": cur_pages, "text": text, "tokens": estimate_tokens(text)})
        cur_text, cur_pages, cur_len = [], [], 0

    for p in pages:
        block = page_block(p)
        if len(block) > budget_chars:
            flush()
            body = p.get("text") or ""
            step = budget_chars - 60
            parts = [body[i:i + step] for i in range(0, len(body), step)] or [""]
            for n, part in enumerate(parts, start=1):
                text = f"=== PAGE {p['page']} (part {n}/{len(parts)}) ===\n{part}"
                chunks.append({"pages": [p["page"]], "text": text, "tokens": estimate_tokens(text)})
            continue
        if cur_len + len(block) > budget_chars:
            flush()
        cur_text.append(block)
        cur_pages.append(p["page"])
        cur_len += len(block) + 2
    flush()
    return chunks
