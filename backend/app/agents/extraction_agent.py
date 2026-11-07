"""Cross-Model Extraction Agent: the N² (3 × 3) competition orchestrator.

Every cell receives exactly: the same processed document content, the same
original requirement workbook, one *unchanged* generated prompt (as the system
message) and the common JSON output contract. Cells run concurrently (bounded by
the LLM client's semaphore) and never see each other's outputs.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents import document_agent, validation_agent
from app.core.config import MODEL_SLOTS, Settings
from app.core.errors import ConfigurationError, ConflictError, ValidationFailed
from app.core.utils import extract_json_object, new_id, utcnow
from app.db.repository import Repository
from app.schemas.requirement import CanonicalField, RequirementSet
from app.services.groq_client import LLMClient, LLMError

log = logging.getLogger("n2.extraction")

TERMINAL = {"completed", "failed", "skipped"}


def build_output_contract(fields: list[CanonicalField]) -> str:
    lines = [f'    "{f.key}": {{"value": <{f.data_type} or null>, "evidence": <verbatim quote or null>, '
             f'"page": <integer or null>}}' for f in fields]
    key_list = "\n".join(f"- {f.key} ({f.data_type}{', mandatory' if f.mandatory else ''}): {f.label}" for f in fields)
    return (
        "=== COMMON OUTPUT CONTRACT (applies to every extraction; mandatory) ===\n"
        "Return ONLY a single JSON object with this exact structure and no other text:\n"
        "{\n"
        '  "prompt_generator": "<prompt id you were given>",\n'
        '  "extraction_model": "<your model id>",\n'
        '  "extracted_fields": {\n' + ",\n".join(lines) + "\n  }\n}\n"
        "Rules:\n"
        "- Include every key listed below exactly once, spelled exactly as given.\n"
        "- If a value is not explicitly present in the document, set value, evidence and page to null. "
        "Never guess or invent values.\n"
        "- evidence must be copied verbatim from the document text; page is the number from the nearest "
        "preceding '=== PAGE n ===' marker.\n"
        f"Field keys:\n{key_list}"
    )


def build_extraction_messages(prompt_text: str, prompt_id: str, extraction_model: str, contract: str,
                              requirements_text: str, chunk: dict[str, Any], chunk_index: int,
                              chunk_total: int) -> list[dict[str, str]]:
    scope = f"pages {chunk['pages'][0]}-{chunk['pages'][-1]}" if chunk["pages"] else "document"
    part = f" — part {chunk_index}/{chunk_total} of the document; extract only what appears in this part" \
        if chunk_total > 1 else ""
    user = (
        f"{contract}\n\nprompt_generator = \"{prompt_id}\"; extraction_model = \"{extraction_model}\"\n\n"
        f"=== ORIGINAL REQUIREMENT WORKBOOK ===\n{requirements_text}\n\n"
        f"=== DOCUMENT CONTENT ({scope}{part}) ===\n{chunk['text']}"
    )
    # The generated prompt is used verbatim as the system message — never modified.
    return [{"role": "system", "content": prompt_text}, {"role": "user", "content": user}]


def merge_chunk_outputs(objs: list[dict[str, Any]], fields: list[CanonicalField]) -> dict[str, Any]:
    """Merge per-chunk outputs: first non-null value in page order wins."""
    merged: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for obj in objs:
        c = validation_agent.coerce_output(obj)
        meta.setdefault("prompt_generator", c.get("prompt_generator"))
        meta.setdefault("extraction_model", c.get("extraction_model"))
        for k, v in c["extracted_fields"].items():
            if k not in merged or (validation_agent.is_null(merged[k].get("value"))
                                   and not validation_agent.is_null(v.get("value"))):
                merged[k] = v  # keeps the "_scalar" marker so validation can flag bare values
    return {**meta, "extracted_fields": merged}


# ---------------------------------------------------------------------------
# Competition lifecycle
# ---------------------------------------------------------------------------

def create_competition(repo: Repository, settings: Settings, *, prompt_run_id: str, document_id: str) -> dict[str, Any]:
    missing = settings.missing_configuration()
    if missing:
        raise ConfigurationError(f"Missing configuration: {', '.join(missing)}", details={"missing": missing})
    prun = repo.get("prompt_runs", prompt_run_id)
    doc = repo.get("documents", document_id)
    if doc.get("status") != "processed":
        raise ConflictError("Document has not been processed successfully yet")
    if not any(p["status"] == "completed" for p in prun["prompts"]):
        raise ConflictError("No generated prompts are available in this prompt run")
    req = repo.get("requirements", prun["requirement_id"])
    req_set = RequirementSet.model_validate(req["requirement_set"])
    chunks = document_agent.chunk_pages(doc["pages"], settings.max_document_tokens)
    if not chunks:
        raise ValidationFailed("Document has no content to extract from")
    cid = new_id("run")
    comp = repo.insert("competitions", cid, {
        "requirement_id": req["id"],
        "prompt_run_id": prompt_run_id,
        "document_id": document_id,
        "document_name": doc["filename"],
        "requirement_name": req["filename"],
        "models": {p["slot"]: p["model_id"] for p in prun["prompts"]},
        "extraction_models": settings.models,
        "field_count": len(req_set.fields),
        "chunk_count": len(chunks),
        "max_document_tokens": settings.max_document_tokens,
        "started_at": None,
        "finished_at": None,
        "error": None,
    }, parent_id=prompt_run_id, status="queued")
    prompts = {p["slot"]: p for p in prun["prompts"]}
    for gen in MODEL_SLOTS:
        for ext in MODEL_SLOTS:
            p = prompts.get(gen)
            prompt_ok = p is not None and p["status"] == "completed"
            eid = f"{cid}_P{gen[1:]}x{ext}"
            repo.insert("executions", eid, {
                "competition_id": cid,
                "cell": f"P{gen[1:]}×{ext}",
                "prompt_slot": gen,
                "prompt_id": f"P{gen[1:]}",
                "prompt_model": p["model_id"] if p else None,
                "extraction_slot": ext,
                "extraction_model": settings.models[ext],
                "is_self_prompt": gen == ext,
                "attempts": 0,
                "latency_ms": None,
                "usage": {},
                "chunks": [],
                "raw_response": None,
                "normalized": None,
                "validation": None,
                "error": None if prompt_ok else "Prompt generation failed for this generator; cell skipped",
                "started_at": None,
                "finished_at": None,
            }, parent_id=cid, status="queued" if prompt_ok else "skipped")
    return comp


async def run_execution(repo: Repository, client: LLMClient, settings: Settings, execution_id: str, *,
                        prompt_text: str, contract: str, requirements_text: str, chunks: list[dict[str, Any]],
                        fields: list[CanonicalField], pages: list[dict[str, Any]]) -> dict[str, Any]:
    ex = repo.update("executions", execution_id, {"status": "running", "started_at": utcnow(), "error": None,
                                                  "chunks": [], "finished_at": None})
    chunk_records: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    usage_total: dict[str, int] = {}
    latency_total = 0
    attempts_total = 0
    errors: list[str] = []
    try:
        for idx, chunk in enumerate(chunks, start=1):
            messages = build_extraction_messages(prompt_text, ex["prompt_id"], ex["extraction_model"], contract,
                                                 requirements_text, chunk, idx, len(chunks))
            rec: dict[str, Any] = {"index": idx, "pages": chunk["pages"], "est_input_tokens": chunk["tokens"]}
            try:
                res = await client.complete(ex["extraction_model"], messages, json_mode=True)
                latency_total += res.latency_ms
                attempts_total += res.attempts
                for k, v in res.usage.items():
                    usage_total[k] = usage_total.get(k, 0) + v
                rec.update({"status": "completed", "latency_ms": res.latency_ms, "usage": res.usage,
                            "attempts": res.attempts, "raw_response": res.text, "notes": res.notes})
                try:
                    parsed.append(extract_json_object(res.text))
                    rec["json_valid"] = True
                except ValueError as e:
                    rec["json_valid"] = False
                    rec["parse_error"] = str(e)
            except LLMError as e:
                attempts_total += e.attempts
                rec.update({"status": "failed", "error": str(e), "error_kind": e.kind, "attempts": e.attempts})
                errors.append(f"chunk {idx}: {e.kind}: {e}")
            chunk_records.append(rec)
            repo.update("executions", execution_id, {"chunks": chunk_records})

        raw_joined = "\n\n".join(
            (f"--- chunk {r['index']} (pages {r['pages']}) ---\n" if len(chunks) > 1 else "") + (r.get("raw_response") or "")
            for r in chunk_records if r.get("raw_response") is not None
        ) or None
        all_failed = all(r["status"] == "failed" for r in chunk_records)
        if all_failed:
            return repo.update("executions", execution_id, {
                "status": "failed", "error": "; ".join(errors)[:1500], "finished_at": utcnow(),
                "attempts": attempts_total, "usage": usage_total, "latency_ms": latency_total or None,
                "validation": validation_agent._empty_report(fields, json_valid=False,
                                                             error="API call failed").model_dump(),
            })
        if parsed:
            merged = merge_chunk_outputs(parsed, fields)
            report, normalized = validation_agent.validate_extraction(merged, fields, pages)
            if any(not r.get("json_valid", True) for r in chunk_records if r["status"] == "completed"):
                report.json_valid = False
                report.parse_error = "one or more chunks returned malformed JSON"
        else:
            report, normalized = validation_agent.validate_extraction(raw_joined, fields, pages)
        return repo.update("executions", execution_id, {
            "status": "completed",
            "error": "; ".join(errors)[:1500] or None,
            "finished_at": utcnow(),
            "attempts": attempts_total,
            "usage": usage_total,
            "latency_ms": latency_total,
            "raw_response": raw_joined,
            "normalized": normalized,
            "validation": report.model_dump(),
        })
    except asyncio.CancelledError:
        repo.update("executions", execution_id, {"status": "interrupted", "error": "Execution interrupted",
                                                 "finished_at": utcnow(), "chunks": chunk_records})
        raise
    except Exception as e:  # noqa: BLE001 - recorded explicitly, never swallowed silently
        log.exception("execution %s crashed", execution_id)
        return repo.update("executions", execution_id, {"status": "failed", "error": f"internal error: {e}"[:1500],
                                                        "finished_at": utcnow(), "chunks": chunk_records})


async def run_competition(repo: Repository, client: LLMClient, settings: Settings, competition_id: str,
                          *, only_unfinished: bool = False) -> dict[str, Any]:
    comp = repo.update("competitions", competition_id, {"status": "running", "started_at": utcnow(),
                                                        "finished_at": None, "error": None})
    try:
        prun = repo.get("prompt_runs", comp["prompt_run_id"])
        doc = repo.get("documents", comp["document_id"])
        req = repo.get("requirements", comp["requirement_id"])
        req_set = RequirementSet.model_validate(req["requirement_set"])
        chunks = document_agent.chunk_pages(doc["pages"], comp.get("max_document_tokens") or settings.max_document_tokens)
        contract = build_output_contract(req_set.fields)
        prompts = {p["slot"]: p for p in prun["prompts"]}
        executions = repo.list("executions", parent_id=competition_id, order="ASC", limit=50)
        tasks = []
        for ex in executions:
            if ex["status"] == "skipped" or (only_unfinished and ex["status"] == "completed"):
                continue
            prompt = prompts[ex["prompt_slot"]]
            tasks.append(run_execution(
                repo, client, settings, ex["id"], prompt_text=prompt["prompt_text"], contract=contract,
                requirements_text=req["rendered_text"], chunks=chunks, fields=req_set.fields, pages=doc["pages"]))
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        repo.update("competitions", competition_id, {"status": "interrupted", "finished_at": utcnow(),
                                                     "error": "Competition interrupted (server shutdown or cancel)"})
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("competition %s failed", competition_id)
        return repo.update("competitions", competition_id, {"status": "failed", "finished_at": utcnow(),
                                                            "error": str(e)[:1000]})
    final = repo.list("executions", parent_id=competition_id, limit=50)
    n_ok = sum(e["status"] == "completed" for e in final)
    status = "completed" if n_ok == len(final) else ("completed_with_errors" if n_ok else "failed")
    return repo.update("competitions", competition_id, {"status": status, "finished_at": utcnow(),
                                                        "completed_cells": n_ok, "total_cells": len(final)})
