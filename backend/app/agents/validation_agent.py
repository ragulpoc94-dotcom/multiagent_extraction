"""Validation Agent: Pydantic schema validation, type checks, missing-value and
unsupported-value (evidence not found in source) detection."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from app.core.utils import extract_json_object
from app.schemas.extraction import ExtractionOutput, FieldResult, FieldValidation, ValidationReport
from app.schemas.requirement import CanonicalField

NULL_STRINGS = {"", "null", "none", "n/a", "na", "not found", "not available", "not present", "nil", "-", "unknown"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
                "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d-%B-%Y", "%Y%m%d", "%d %b, %Y", "%Y-%m-%dT%H:%M:%S")


def alnum(text: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(text).lower())


def is_null(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in NULL_STRINGS)


def parse_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = re.sub(r"(?i)\b(inr|usd|eur|gbp|rs\.?|cr|dr)\b", "", s)
    s = re.sub(r"[^0-9.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    if s.count(",") and s.count("."):
        # Decide decimal separator by last occurrence.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) in (1, 2):
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


def parse_date(v: Any) -> str | None:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = re.sub(r"\s+", " ", str(v).strip())
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1", "checked", "present"):
        return True
    if s in ("false", "no", "n", "0", "unchecked", "absent"):
        return False
    return None


def normalize_value(value: Any, data_type: str) -> tuple[Any, str | None]:
    """Return (normalized_value, error). Error is None when the type is valid."""
    if data_type == "number":
        n = parse_number(value)
        return (n, None) if n is not None else (None, "not a number")
    if data_type == "integer":
        n = parse_number(value)
        if n is None:
            return None, "not an integer"
        return (int(n), None) if float(n).is_integer() else (None, "not an integer")
    if data_type == "date":
        d = parse_date(value)
        return (d, None) if d else (None, "unrecognised date format")
    if data_type == "boolean":
        b = parse_bool(value)
        return (b, None) if b is not None else (None, "not a boolean")
    if isinstance(value, (dict, list)):
        return str(value), None
    return re.sub(r"\s+", " ", str(value)).strip(), None


def coerce_output(obj: Any) -> dict[str, Any]:
    """Accept the contract shape or a flat {key: ...} object; map scalars to {value}."""
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON is not an object")
    fields = obj.get("extracted_fields")
    if not isinstance(fields, dict):
        fields = {k: v for k, v in obj.items() if k not in ("prompt_generator", "extraction_model")}
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(v, dict) and ({"value", "evidence", "page"} & set(v.keys())):
            out[k] = v
        else:
            out[k] = {"value": v, "evidence": None, "page": None, "_scalar": True}
    return {"prompt_generator": obj.get("prompt_generator"), "extraction_model": obj.get("extraction_model"),
            "extracted_fields": out}


def validate_extraction(raw: str | dict[str, Any] | None, fields: list[CanonicalField],
                        pages: list[dict[str, Any]]) -> tuple[ValidationReport, dict[str, Any] | None]:
    """Validate a raw model response. Returns (report, normalized_output_or_None)."""
    expected = len(fields)
    parse_error = None
    obj: Any = None
    if isinstance(raw, dict):
        obj = raw
    else:
        try:
            obj = extract_json_object(raw or "")
        except ValueError as e:
            parse_error = str(e)
    if obj is None:
        return _empty_report(fields, json_valid=False, error=parse_error), None

    try:
        coerced = coerce_output(obj)
        parsed = ExtractionOutput.model_validate(coerced)
        scalar_keys = {k for k, v in coerced["extracted_fields"].items() if v.get("_scalar")}
    except (ValueError, ValidationError) as e:
        return _empty_report(fields, json_valid=True, schema_valid=False, error=f"schema: {e}"[:600]), None

    page_text = {p["page"]: alnum(p.get("text") or "") for p in pages}
    full_text = "".join(page_text.values())
    n_pages = len(pages)
    canonical_keys = {f.key for f in fields}
    returned = parsed.extracted_fields
    results: dict[str, FieldValidation] = {}

    for f in fields:
        fr: FieldResult | None = returned.get(f.key)
        if fr is None:
            results[f.key] = FieldValidation(key=f.key, status="not_returned", issues=["field absent from response"])
            continue
        issues: list[str] = []
        if f.key in scalar_keys:
            issues.append("returned as bare value without evidence object")
        if is_null(fr.value):
            results[f.key] = FieldValidation(key=f.key, status="missing", value=None, evidence=fr.evidence,
                                             page=fr.page, issues=issues)
            continue
        norm, type_err = normalize_value(fr.value, f.data_type)
        if type_err is None and f.allowed_values:
            allowed = {alnum(a) for a in f.allowed_values}
            if alnum(norm) not in allowed:
                type_err = "value not in allowed values"
        evidence_found: bool | None = None
        if fr.evidence and alnum(fr.evidence):
            ev = alnum(fr.evidence)
            if fr.page is not None and fr.page in page_text and ev in page_text[fr.page]:
                evidence_found = True
            elif ev in full_text:
                evidence_found = True
                if fr.page is not None:
                    issues.append("evidence found on a different page than reported")
            else:
                evidence_found = False
                issues.append("evidence text not found in document")
        else:
            issues.append("no evidence provided for non-null value")
        page_bad = fr.page is not None and not (1 <= fr.page <= n_pages)
        if page_bad:
            issues.append(f"page {fr.page} outside document range 1-{n_pages}")
        if type_err:
            status = "type_error"
            issues.append(type_err)
        elif evidence_found is not True:
            status = "unsupported"
        elif page_bad:
            status = "page_invalid"
        else:
            status = "ok"
        results[f.key] = FieldValidation(key=f.key, status=status, value=fr.value, normalized_value=norm,
                                         evidence=fr.evidence, page=fr.page, evidence_found=evidence_found,
                                         issues=issues)

    counts = {s: sum(1 for r in results.values() if r.status == s)
              for s in ("ok", "missing", "not_returned", "type_error", "unsupported", "page_invalid")}
    report = ValidationReport(
        json_valid=True,
        schema_valid=True,
        fields_expected=expected,
        fields_returned=sum(1 for k in canonical_keys if k in returned),
        fields_filled=expected - counts["missing"] - counts["not_returned"],
        missing=counts["missing"],
        not_returned=counts["not_returned"],
        type_errors=counts["type_error"],
        unsupported=counts["unsupported"],
        unexpected_keys=sorted(k for k in returned if k not in canonical_keys),
        missing_rate=round((counts["missing"] + counts["not_returned"]) / expected, 4) if expected else 0.0,
        supported_fill_rate=round(counts["ok"] / expected, 4) if expected else 0.0,
        fields=results,
    )
    normalized = {
        "prompt_generator": parsed.prompt_generator,
        "extraction_model": parsed.extraction_model,
        "extracted_fields": {k: {"value": (None if is_null(v.value) else v.value), "evidence": v.evidence,
                                 "page": v.page} for k, v in returned.items() if k in canonical_keys},
    }
    return report, normalized


def _empty_report(fields: list[CanonicalField], *, json_valid: bool, schema_valid: bool = False,
                  error: str | None = None) -> ValidationReport:
    n = len(fields)
    return ValidationReport(
        json_valid=json_valid, schema_valid=schema_valid, parse_error=error, fields_expected=n, fields_returned=0,
        fields_filled=0, missing=0, not_returned=n, type_errors=0, unsupported=0, missing_rate=1.0 if n else 0.0,
        supported_fill_rate=0.0,
        fields={f.key: FieldValidation(key=f.key, status="not_returned", issues=["no valid output"]) for f in fields},
    )
