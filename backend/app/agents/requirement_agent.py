"""Requirement Understanding Agent.

1. Deterministically parses the workbook into a canonical field schema (used
   for output validation).
2. Sends the *same* rendered workbook to each of the three models, which
   independently return their own structured interpretation.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import MODEL_SLOTS, Settings
from app.core.errors import ConfigurationError
from app.core.utils import extract_json_object, new_id, slugify_key, utcnow
from app.db.repository import Repository
from app.schemas.requirement import InterpretedField, ModelInterpretation, RequirementSet
from app.services import excel_service
from app.services.groq_client import LLMClient, LLMError

UNDERSTAND_SYSTEM = (
    "You are a meticulous business analyst for document-extraction projects. You read requirement "
    "workbooks and restate the extraction requirements precisely. You never invent fields that are not "
    "in the workbook. Respond with a single JSON object only."
)

UNDERSTAND_USER = """Below is an extraction-requirements workbook rendered as markdown tables (all sheets).

Interpret it and return JSON with exactly this structure:
{{
  "summary": "<2-4 sentences: what document type and what must be extracted>",
  "fields": [
    {{"key": "<snake_case key>", "name": "<field name as written>", "description": "<meaning>",
      "type": "<string|number|integer|date|boolean>", "mandatory": <true|false>,
      "rules": ["<field-specific extraction / validation rule>", "..."]}}
  ],
  "business_rules": ["<workbook-level rule>", "..."],
  "ambiguities": ["<anything unclear or contradictory in the requirements>", "..."]
}}

Include every field the workbook asks to extract, in workbook order.

=== REQUIREMENT WORKBOOK ===
{workbook}
"""


def ingest(repo: Repository, content: bytes, filename: str) -> dict[str, Any]:
    sheets = excel_service.read_workbook(content, filename)
    req_set = excel_service.build_requirement_set(sheets)
    rendered = excel_service.render_requirements_text(sheets)
    rid = new_id("req")
    return repo.insert("requirements", rid, {
        "filename": filename,
        "sheets_raw": sheets,
        "requirement_set": req_set.model_dump(),
        "rendered_text": rendered,
        "interpretations": [],
    }, status="parsed")


def _coverage(fields: list[InterpretedField], req_set: RequirementSet) -> float:
    canonical = {f.key for f in req_set.fields}
    labels = {slugify_key(f.label): f.key for f in req_set.fields}
    hit: set[str] = set()
    for f in fields:
        for cand in (f.key, f.name):
            if not cand:
                continue
            k = slugify_key(cand)
            if k in canonical:
                hit.add(k)
            elif k in labels:
                hit.add(labels[k])
    return round(len(hit) / len(canonical), 4) if canonical else 0.0


async def interpret_with_model(client: LLMClient, settings: Settings, slot: str, model_id: str,
                               rendered: str, req_set: RequirementSet) -> ModelInterpretation:
    messages = [
        {"role": "system", "content": UNDERSTAND_SYSTEM},
        {"role": "user", "content": UNDERSTAND_USER.format(workbook=rendered)},
    ]
    try:
        res = await client.complete(model_id, messages, json_mode=True, max_tokens=settings.max_output_tokens)
    except LLMError as e:
        return ModelInterpretation(slot=slot, model_id=model_id, status="failed", error=str(e), created_at=utcnow())
    try:
        obj = extract_json_object(res.text)
        fields = [InterpretedField.model_validate(f) for f in obj.get("fields", []) if isinstance(f, dict)]
        rules = [str(r) for r in obj.get("business_rules", []) or []]
        amb = [str(a) for a in obj.get("ambiguities", []) or []]
        return ModelInterpretation(
            slot=slot, model_id=model_id, status="completed", summary=obj.get("summary"), fields=fields,
            business_rules=rules, ambiguities=amb, coverage=_coverage(fields, req_set), raw_response=res.text,
            latency_ms=res.latency_ms, usage=res.usage, created_at=utcnow(),
        )
    except (ValueError, AttributeError, TypeError) as e:
        return ModelInterpretation(slot=slot, model_id=model_id, status="failed", raw_response=res.text,
                                   error=f"Unparseable interpretation: {e}", latency_ms=res.latency_ms,
                                   usage=res.usage, created_at=utcnow())


async def understand(repo: Repository, client: LLMClient, settings: Settings, requirement_id: str) -> dict[str, Any]:
    missing = settings.missing_configuration()
    if missing:
        raise ConfigurationError(f"Missing configuration: {', '.join(missing)}", details={"missing": missing})
    rec = repo.get("requirements", requirement_id)
    req_set = RequirementSet.model_validate(rec["requirement_set"])
    results = await asyncio.gather(*[
        interpret_with_model(client, settings, slot, settings.models[slot], rec["rendered_text"], req_set)  # type: ignore[arg-type]
        for slot in MODEL_SLOTS
    ])
    return repo.update("requirements", requirement_id, {
        "interpretations": [r.model_dump() for r in results],
        "status": "understood",
    })
