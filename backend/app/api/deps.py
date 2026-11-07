from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request, UploadFile

from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.db.repository import Repository
from app.jobs.runner import JobRunner
from app.services.groq_client import LLMClient


@dataclass
class AppContext:
    settings: Settings
    repo: Repository
    client: LLMClient
    runner: JobRunner


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def read_upload(file: UploadFile, settings: Settings) -> tuple[bytes, str]:
    content = await file.read()
    if not content:
        raise ValidationFailed("Uploaded file is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"File exceeds {settings.max_upload_mb} MB limit")
    return content, file.filename or "upload"


def public_requirement(rec: dict[str, Any], *, include_text: bool = True) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if k != "sheets_raw"}
    if not include_text:
        out.pop("rendered_text", None)
    return out


def public_document(rec: dict[str, Any], *, include_text: bool = True) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if k != "path"}
    if not include_text:
        out["pages"] = [{k: v for k, v in p.items() if k != "text"} for p in rec.get("pages") or []]
    return out
