"""Versioned REST API (v1). All responses use the {success, data, error, meta} envelope."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.agents import document_agent, evaluation_agent, extraction_agent, prompt_agent, requirement_agent
from app.api.deps import AppContext, get_ctx, public_document, public_requirement, read_upload
from app.core.config import MODEL_SLOTS
from app.core.errors import ConflictError, NotFoundError, UpstreamError, ok
from app.services import document_service, export_service
from app.services.groq_client import LLMError

router = APIRouter(prefix="/api/v1")
VERSION = "1.0.0"


# ---------------------------------------------------------------- health / models
@router.get("/health")
async def health(ctx: AppContext = Depends(get_ctx)):
    return ok({
        "status": "ok",
        "version": VERSION,
        "groq_sdk_installed": importlib.util.find_spec("groq") is not None,
        "pdf_engine": "pymupdf" if document_service.fitz is not None else "pypdf",
        "ocr_available": document_service.ocr_available(),
        "configuration_missing": ctx.settings.missing_configuration(),
    })


@router.get("/models")
async def models(ctx: AppContext = Depends(get_ctx)):
    s = ctx.settings
    return ok({
        "api_key_configured": s.api_key_configured,
        "missing": s.missing_configuration(),
        "models": [{"slot": slot, "env_var": f"MODEL_{slot[1:]}", "model_id": s.models[slot]} for slot in MODEL_SLOTS],
        "limits": {"max_concurrency": s.max_concurrency, "max_retries": s.max_retries,
                   "requests_per_minute": s.requests_per_minute, "max_document_tokens": s.max_document_tokens},
    })


@router.get("/models/verify")
async def verify_models(ctx: AppContext = Depends(get_ctx)):
    s = ctx.settings
    if not s.api_key_configured:
        return ok({"verified": False, "reason": "GROQ_API_KEY is not configured", "models": []})
    try:
        available = await ctx.client.list_models()
    except LLMError as e:
        raise UpstreamError(f"Could not list Groq models: {e}", details={"kind": e.kind}) from e
    except Exception as e:  # noqa: BLE001
        raise UpstreamError(f"Could not list Groq models: {e}") from e
    avail = set(available)
    result = [{"slot": slot, "model_id": s.models[slot],
               "available": bool(s.models[slot]) and s.models[slot] in avail} for slot in MODEL_SLOTS]
    return ok({"verified": all(r["available"] for r in result), "models": result, "account_model_count": len(avail)})


# ---------------------------------------------------------------- overview
@router.get("/overview")
async def overview(ctx: AppContext = Depends(get_ctx)):
    repo = ctx.repo
    comps = repo.list("competitions", limit=20)
    recent = []
    total_done = total_failed = 0
    for c in comps:
        execs = repo.list("executions", parent_id=c["id"], limit=50)
        done = sum(e["status"] == "completed" for e in execs)
        failed = sum(e["status"] in ("failed", "interrupted") for e in execs)
        total_done += done
        total_failed += failed
        ev = repo.find("evaluations", f"eval_{c['id']}") or {}
        bc = ev.get("best_combination") or {}
        recent.append({
            "id": c["id"], "status": c["status"], "created_at": c["created_at"], "document_name": c.get("document_name"),
            "requirement_name": c.get("requirement_name"), "completed_cells": done, "failed_cells": failed,
            "total_cells": len(execs),
            "best_combination": {k: bc.get(k) for k in ("cell", "prompt_model", "extraction_model")} if bc else None,
            "primary_metric": ev.get("primary_metric"),
            "best_score": bc.get(ev.get("primary_metric", "")) if bc else None,
            "has_golden_labels": ev.get("has_golden_labels", False),
        })
    return ok({
        "counts": {
            "requirements": len(repo.list("requirements", limit=1000)),
            "prompt_runs": len(repo.list("prompt_runs", limit=1000)),
            "documents": len(repo.list("documents", limit=1000)),
            "competitions": len(repo.list("competitions", limit=1000)),
            "completed_executions": total_done,
            "failed_executions": total_failed,
        },
        "recent_competitions": recent,
    })


# ---------------------------------------------------------------- requirements
@router.post("/requirements/upload", status_code=201)
async def upload_requirements(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)):
    content, name = await read_upload(file, ctx.settings)
    if not name.lower().endswith((".xlsx", ".xlsm", ".xls", ".csv")):
        from app.core.errors import ValidationFailed
        raise ValidationFailed("Requirement file must be an Excel workbook (.xlsx/.xlsm/.xls) or .csv")
    rec = requirement_agent.ingest(ctx.repo, content, name)
    return ok(public_requirement(rec))


@router.get("/requirements")
async def list_requirements(ctx: AppContext = Depends(get_ctx)):
    return ok([{
        "id": r["id"], "filename": r["filename"], "status": r["status"], "created_at": r["created_at"],
        "field_count": len(r["requirement_set"]["fields"]), "sheet_count": len(r["requirement_set"]["sheets"]),
    } for r in ctx.repo.list("requirements", limit=100)])


@router.get("/requirements/{requirement_id}")
async def get_requirement(requirement_id: str, ctx: AppContext = Depends(get_ctx)):
    return ok(public_requirement(ctx.repo.get("requirements", requirement_id)))


@router.post("/requirements/{requirement_id}/understand")
async def understand_requirements(requirement_id: str, ctx: AppContext = Depends(get_ctx)):
    rec = await requirement_agent.understand(ctx.repo, ctx.client, ctx.settings, requirement_id)
    return ok(public_requirement(rec))


# ---------------------------------------------------------------- prompts
class PromptGenerateRequest(BaseModel):
    requirement_id: str


@router.post("/prompts/generate", status_code=201)
async def generate_prompts(body: PromptGenerateRequest, ctx: AppContext = Depends(get_ctx)):
    return ok(await prompt_agent.generate(ctx.repo, ctx.client, ctx.settings, body.requirement_id))


@router.get("/prompts")
async def list_prompt_runs(requirement_id: str | None = None, ctx: AppContext = Depends(get_ctx)):
    runs = ctx.repo.list("prompt_runs", parent_id=requirement_id, limit=100)
    return ok([{"id": r["id"], "requirement_id": r["requirement_id"], "status": r["status"], "created_at": r["created_at"],
                "prompts": [{"prompt_id": p["prompt_id"], "model_id": p["model_id"], "status": p["status"]}
                            for p in r["prompts"]]} for r in runs])


@router.get("/prompts/{run_id}")
async def get_prompt_run(run_id: str, ctx: AppContext = Depends(get_ctx)):
    return ok(ctx.repo.get("prompt_runs", run_id))


# ---------------------------------------------------------------- documents
@router.post("/documents/upload", status_code=201)
async def upload_document(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)):
    content, name = await read_upload(file, ctx.settings)
    return ok(public_document(document_agent.save_upload(ctx.repo, ctx.settings, content, name)))


@router.post("/documents/{document_id}/process")
async def process_document(document_id: str, ctx: AppContext = Depends(get_ctx)):
    rec = await document_agent.process(ctx.repo, ctx.settings, document_id)
    return ok(public_document(rec))


@router.get("/documents")
async def list_documents(ctx: AppContext = Depends(get_ctx)):
    return ok([public_document(d, include_text=False) for d in ctx.repo.list("documents", limit=100)])


@router.get("/documents/{document_id}")
async def get_document(document_id: str, ctx: AppContext = Depends(get_ctx)):
    return ok(public_document(ctx.repo.get("documents", document_id)))


@router.get("/documents/{document_id}/file")
async def document_file(document_id: str, ctx: AppContext = Depends(get_ctx)):
    rec = ctx.repo.get("documents", document_id)
    return FileResponse(rec["path"], media_type=rec["mime"], filename=rec["filename"],
                        content_disposition_type="inline")


@router.get("/documents/{document_id}/pages/{page}/image")
async def document_page_image(document_id: str, page: int, ctx: AppContext = Depends(get_ctx)):
    rec = ctx.repo.get("documents", document_id)
    import asyncio
    png = await asyncio.to_thread(document_service.render_page_png, Path(rec["path"]).read_bytes(), rec["filename"], page)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


# ---------------------------------------------------------------- competitions
class CompetitionCreate(BaseModel):
    prompt_run_id: str
    document_id: str
    auto_start: bool = True


def _cell_summary(e: dict) -> dict:
    v = e.get("validation") or {}
    return {
        "id": e["id"], "cell": e["cell"], "prompt_slot": e["prompt_slot"], "prompt_id": e["prompt_id"],
        "prompt_model": e.get("prompt_model"), "extraction_slot": e["extraction_slot"],
        "extraction_model": e["extraction_model"], "is_self_prompt": e["is_self_prompt"], "status": e["status"],
        "latency_ms": e.get("latency_ms"), "usage": e.get("usage") or {}, "attempts": e.get("attempts"),
        "json_valid": v.get("json_valid") if v else None, "schema_valid": v.get("schema_valid") if v else None,
        "missing_rate": v.get("missing_rate") if v else None,
        "supported_fill_rate": v.get("supported_fill_rate") if v else None,
        "chunks_done": len(e.get("chunks") or []), "error": e.get("error"),
        "started_at": e.get("started_at"), "finished_at": e.get("finished_at"),
    }


@router.post("/competitions", status_code=201)
async def create_competition(body: CompetitionCreate, ctx: AppContext = Depends(get_ctx)):
    comp = extraction_agent.create_competition(ctx.repo, ctx.settings, prompt_run_id=body.prompt_run_id,
                                               document_id=body.document_id)
    if body.auto_start:
        ctx.runner.start(comp["id"])
    return ok(comp)


@router.get("/competitions")
async def list_competitions(ctx: AppContext = Depends(get_ctx)):
    return ok(ctx.repo.list("competitions", limit=100))


@router.get("/competitions/{run_id}")
async def get_competition(run_id: str, ctx: AppContext = Depends(get_ctx)):
    comp = ctx.repo.get("competitions", run_id)
    comp["is_running"] = ctx.runner.is_running(run_id)
    return ok(comp)


@router.get("/competitions/{run_id}/status")
async def competition_status(run_id: str, ctx: AppContext = Depends(get_ctx)):
    comp = ctx.repo.get("competitions", run_id)
    cells = [_cell_summary(e) for e in ctx.repo.list("executions", parent_id=run_id, order="ASC", limit=50)]
    counts: dict[str, int] = {}
    for c in cells:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return ok({"id": run_id, "status": comp["status"], "is_running": ctx.runner.is_running(run_id),
               "started_at": comp.get("started_at"), "finished_at": comp.get("finished_at"), "error": comp.get("error"),
               "chunk_count": comp.get("chunk_count"), "counts": counts, "cells": cells})


@router.post("/competitions/{run_id}/start")
async def start_competition(run_id: str, ctx: AppContext = Depends(get_ctx)):
    comp = ctx.repo.get("competitions", run_id)
    if comp["status"] not in ("queued",):
        raise ConflictError(f"Competition is '{comp['status']}'; use resume for interrupted/failed runs")
    ctx.runner.start(run_id)
    return ok({"id": run_id, "started": True})


@router.post("/competitions/{run_id}/resume")
async def resume_competition(run_id: str, ctx: AppContext = Depends(get_ctx)):
    comp = ctx.repo.get("competitions", run_id)
    if comp["status"] == "completed":
        raise ConflictError("Competition already completed successfully")
    ctx.runner.start(run_id, only_unfinished=True)
    return ok({"id": run_id, "resumed": True})


@router.get("/competitions/{run_id}/results")
async def competition_results(run_id: str, ctx: AppContext = Depends(get_ctx)):
    comp = ctx.repo.get("competitions", run_id)
    req = ctx.repo.get("requirements", comp["requirement_id"])
    execs = ctx.repo.list("executions", parent_id=run_id, order="ASC", limit=50)
    return ok({"competition": comp, "fields": req["requirement_set"]["fields"],
               "executions": [{k: v for k, v in e.items() if k not in ("raw_response", "chunks")} for e in execs]})


@router.get("/competitions/{run_id}/executions/{execution_id}")
async def get_execution(run_id: str, execution_id: str, ctx: AppContext = Depends(get_ctx)):
    ex = ctx.repo.get("executions", execution_id)
    if ex["competition_id"] != run_id:
        raise NotFoundError("Execution does not belong to this competition")
    return ok(ex)


# ---------------------------------------------------------------- evaluations
@router.post("/evaluations/{run_id}")
async def evaluate(run_id: str, golden: UploadFile | None = File(default=None), ctx: AppContext = Depends(get_ctx)):
    upload = None
    if golden is not None and golden.filename:
        upload = await read_upload(golden, ctx.settings)
    if ctx.runner.is_running(run_id):
        raise ConflictError("Competition is still running; evaluate after it finishes")
    return ok(evaluation_agent.run_evaluation(ctx.repo, run_id, upload))


@router.delete("/evaluations/{run_id}/golden")
async def clear_golden(run_id: str, ctx: AppContext = Depends(get_ctx)):
    ctx.repo.get("competitions", run_id)
    return ok(evaluation_agent.run_evaluation(ctx.repo, run_id, None, keep_existing_golden=False))


@router.get("/evaluations/{run_id}")
async def get_evaluation(run_id: str, ctx: AppContext = Depends(get_ctx)):
    ev = ctx.repo.find("evaluations", f"eval_{run_id}")
    if ev is None:
        ctx.repo.get("competitions", run_id)
        raise NotFoundError("No evaluation yet for this competition")
    return ok(ev)


# ---------------------------------------------------------------- exports
ExportKind = Literal["consolidated", "prompts", "execution", "csv", "xlsx"]


@router.get("/exports/{run_id}")
async def export(run_id: str, kind: ExportKind = Query("consolidated"), execution_id: str | None = None,
                 ctx: AppContext = Depends(get_ctx)):
    data = export_service.gather(ctx.repo, run_id)
    if kind == "csv":
        return _download(export_service.csv_export(data), f"{run_id}_comparison.csv", "text/csv")
    if kind == "xlsx":
        return _download(export_service.excel_export(data), f"{run_id}_evaluation_report.xlsx",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if kind == "prompts":
        payload, name = export_service.prompts_export(data), f"{run_id}_prompts.json"
    elif kind == "execution":
        ex = next((e for e in data["executions"] if e["id"] == execution_id), None)
        if ex is None:
            raise NotFoundError("execution_id is required and must belong to this competition")
        payload, name = export_service.execution_export(ex), f"{execution_id}.json"
    else:
        payload, name = export_service.consolidated_export(data), f"{run_id}_consolidated.json"
    return _download(json.dumps(payload, indent=2, default=str).encode(), name, "application/json")


def _download(content: bytes, filename: str, media: str) -> StreamingResponse:
    return StreamingResponse(io.BytesIO(content), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
