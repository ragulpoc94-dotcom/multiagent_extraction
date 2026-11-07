"""Prompt Generation Agent.

Each of the three models independently writes its own extraction prompt from
the same requirement workbook (plus, if available, *its own* interpretation).
Prompts are stored verbatim and never edited afterwards.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from app.core.config import MODEL_SLOTS, Settings
from app.core.errors import ConfigurationError, ValidationFailed
from app.core.utils import new_id, strip_code_fences, utcnow
from app.db.repository import Repository
from app.schemas.requirement import RequirementSet
from app.services.groq_client import LLMClient, LLMError

PROMPT_GEN_SYSTEM = (
    "You are an expert prompt engineer specialising in high-precision, atomic, field-level information "
    "extraction from business documents with large language models. You write prompts that other models "
    "follow exactly."
)

PROMPT_GEN_USER = """Write a complete SYSTEM PROMPT that instructs an extraction model to extract the fields
defined in the requirement workbook below from a single document.

Your prompt MUST:
1. Cover every field, one by one (atomic, field-level), with precise per-field instructions derived from the workbook
   (meaning, expected type/format, rules, where it is typically found, how to disambiguate).
2. Specify missing-value handling: if a value is not explicitly present in the document, the model must return
   null for value, evidence and page — never guess, infer or invent values.
3. Require evidence for every non-null value: a short verbatim quote copied exactly from the document text, plus the
   page number taken from the "=== PAGE n ===" markers.
4. Include normalisation guidance for dates, numbers, amounts and booleans consistent with the workbook.
5. Instruct the model to return ONLY a JSON object (no prose, no markdown).

The extraction model will separately receive a fixed JSON output contract listing these exact field keys,
so refer to fields by these keys: {keys}

Output ONLY the prompt text itself. Do not add commentary before or after it.

=== REQUIREMENT WORKBOOK ===
{workbook}
{interpretation}"""


def build_generation_messages(rendered: str, req_set: RequirementSet, interpretation: dict[str, Any] | None) -> list[dict[str, str]]:
    interp_text = ""
    if interpretation and interpretation.get("status") == "completed":
        interp_text = (
            "\n=== YOUR OWN EARLIER INTERPRETATION OF THESE REQUIREMENTS ===\n"
            f"Summary: {interpretation.get('summary') or ''}\n"
            "Business rules: " + "; ".join(interpretation.get("business_rules") or []) + "\n"
            "Ambiguities you noted: " + "; ".join(interpretation.get("ambiguities") or [])
        )
    return [
        {"role": "system", "content": PROMPT_GEN_SYSTEM},
        {"role": "user", "content": PROMPT_GEN_USER.format(
            keys=", ".join(req_set.field_keys()), workbook=rendered, interpretation=interp_text)},
    ]


def static_checks(prompt: str, req_set: RequirementSet) -> dict[str, Any]:
    """Transparent, rule-based checks of a generated prompt (not an LLM score)."""
    low = prompt.lower()
    keys = req_set.field_keys()
    mentioned = [k for k in keys if k.lower() in low or k.replace("_", " ") in low]
    return {
        "field_key_coverage": round(len(mentioned) / len(keys), 4) if keys else 0.0,
        "fields_not_mentioned": [k for k in keys if k not in mentioned],
        "mentions_null_handling": bool(re.search(r"\bnull\b|missing|not (present|found)", low)),
        "mentions_evidence": "evidence" in low or "quote" in low,
        "mentions_page": "page" in low,
        "requests_json_only": "json" in low,
        "characters": len(prompt),
    }


async def generate_one(client: LLMClient, settings: Settings, slot: str, model_id: str, rendered: str,
                       req_set: RequirementSet, interpretation: dict[str, Any] | None) -> dict[str, Any]:
    started = utcnow()
    messages = build_generation_messages(rendered, req_set, interpretation)
    base = {"slot": slot, "prompt_id": f"P{slot[1:]}", "model_id": model_id, "started_at": started,
            "used_own_interpretation": bool(interpretation and interpretation.get("status") == "completed")}
    try:
        res = await client.complete(model_id, messages, json_mode=False, max_tokens=settings.prompt_max_output_tokens,
                                    temperature=0.2)
    except LLMError as e:
        return {**base, "status": "failed", "error": str(e), "prompt_text": None, "created_at": utcnow()}
    text = strip_code_fences(res.text)
    if len(text) < 40:
        return {**base, "status": "failed", "error": "Model returned an empty or trivially short prompt",
                "prompt_text": text or None, "latency_ms": res.latency_ms, "usage": res.usage, "created_at": utcnow()}
    return {**base, "status": "completed", "prompt_text": text, "latency_ms": res.latency_ms, "usage": res.usage,
            "attempts": res.attempts, "checks": static_checks(text, req_set), "created_at": utcnow()}


async def generate(repo: Repository, client: LLMClient, settings: Settings, requirement_id: str) -> dict[str, Any]:
    missing = settings.missing_configuration()
    if missing:
        raise ConfigurationError(f"Missing configuration: {', '.join(missing)}", details={"missing": missing})
    rec = repo.get("requirements", requirement_id)
    req_set = RequirementSet.model_validate(rec["requirement_set"])
    if not req_set.fields:
        raise ValidationFailed("Requirement set has no fields")
    interps = {i["slot"]: i for i in rec.get("interpretations") or []}
    prompts = await asyncio.gather(*[
        generate_one(client, settings, slot, settings.models[slot], rec["rendered_text"], req_set,  # type: ignore[arg-type]
                     interps.get(slot))
        for slot in MODEL_SLOTS
    ])
    ok_count = sum(p["status"] == "completed" for p in prompts)
    status = "completed" if ok_count == 3 else ("partial" if ok_count else "failed")
    run_id = new_id("prun")
    return repo.insert("prompt_runs", run_id, {
        "requirement_id": requirement_id,
        "models": settings.models,
        "prompts": prompts,
    }, parent_id=requirement_id, status=status)
