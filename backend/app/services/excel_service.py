"""Dynamic Excel requirement discovery.

Discovers sheets, header rows, column roles (field / description / type /
mandatory / instructions / examples / allowed values) and business-rule sheets
from arbitrary workbooks. No extraction field is hardcoded: the canonical
schema is whatever the workbook defines.
"""
from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

from app.core.errors import ValidationFailed
from app.core.utils import slugify_key
from app.schemas.requirement import CanonicalField, RequirementSet, SheetPreview

PREVIEW_ROWS = 50
MAX_ROWS_PER_SHEET = 2000

ROLE_SYNONYMS: dict[str, list[str]] = {
    "field": ["field name", "field", "attribute name", "attribute", "data element", "element name", "element",
              "data field", "column name", "field label", "label", "parameter", "data point", "item", "name", "key",
              "entity"],
    "description": ["description", "field description", "definition", "meaning", "details", "explanation"],
    "data_type": ["data type", "datatype", "type", "field type", "format", "value type", "expected format"],
    "mandatory": ["mandatory", "required", "is mandatory", "is required", "mandatory/optional", "m/o", "optional",
                  "requirement level", "obligation"],
    "instructions": ["extraction instruction", "extraction instructions", "instructions", "instruction",
                     "extraction rule", "extraction logic", "business rule", "business rules", "rules", "rule",
                     "logic", "guidelines", "how to extract", "validation", "validation rule", "notes", "remarks",
                     "comments", "source location", "location"],
    "examples": ["example", "examples", "sample", "sample value", "example value"],
    "allowed_values": ["allowed values", "valid values", "permitted values", "list of values", "lov", "enum",
                       "possible values", "values"],
}

NOTE_SHEET_HINTS = ("rule", "instruction", "guideline", "note", "readme", "read me", "overview", "policy")

TRUE_WORDS = {"y", "yes", "true", "1", "m", "mandatory", "required", "must", "compulsory"}


def _norm(h: Any) -> str:
    return re.sub(r"\s+", " ", str(h)).strip().lower().replace("_", " ")


def normalize_type(raw: Any) -> str:
    t = _norm(raw) if raw is not None else ""
    if not t or t == "nan":
        return "string"
    if any(w in t for w in ("alphanumeric", "alpha-numeric", "text", "string", "char")):
        return "string"
    if any(w in t for w in ("bool", "yes/no", "y/n", "flag", "true/false")):
        return "boolean"
    if any(w in t for w in ("date", "dob", "timestamp", "datetime", "dd/", "mm/", "yyyy")):
        return "date"
    if re.search(r"\b(int|integer|whole number|count)\b", t):
        return "integer"
    if any(w in t for w in ("number", "numeric", "decimal", "amount", "currency", "float", "money", "percent",
                            "double", "rate")):
        return "number"
    return "string"


def parse_mandatory(raw: Any) -> bool:
    if raw is None:
        return False
    t = _norm(raw)
    if t in ("", "nan", "none"):
        return False
    if t in TRUE_WORDS:
        return True
    return t.startswith("mandatory") or t.startswith("required") or t == "m"


def detect_roles(columns: list[str]) -> dict[str, str]:
    """Greedy best-match assignment of semantic roles to columns."""
    candidates: list[tuple[int, str, str]] = []
    for col in columns:
        h = _norm(col)
        if not h or h.startswith("unnamed"):
            continue
        for role, syns in ROLE_SYNONYMS.items():
            best = 0
            for rank, s in enumerate(syns):
                if h == s:
                    best = max(best, 1000 - rank)
                elif re.search(rf"\b{re.escape(s)}\b", h):
                    best = max(best, 500 - rank + len(s))
            if best:
                candidates.append((best, role, col))
    candidates.sort(reverse=True)
    roles: dict[str, str] = {}
    used: set[str] = set()
    for _score, role, col in candidates:
        if role in roles or col in used:
            continue
        roles[role] = col
        used.add(col)
    return roles


def _find_header_row(raw: pd.DataFrame) -> int | None:
    for idx in range(min(len(raw), 25)):
        values = [v for v in raw.iloc[idx].tolist() if pd.notna(v) and str(v).strip()]
        if len(values) >= 2:
            return idx
    for idx in range(min(len(raw), 25)):
        if any(pd.notna(v) and str(v).strip() for v in raw.iloc[idx].tolist()):
            return idx
    return None


def _clean(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def read_workbook(content: bytes, filename: str = "requirements.xlsx") -> dict[str, list[dict[str, Any]] | Any]:
    """Return {sheet_name: {"columns": [...], "rows": [...]}} with header rows auto-detected."""
    try:
        engine = None if filename.lower().endswith((".xlsx", ".xlsm")) else None
        if filename.lower().endswith(".csv"):
            frames = {"Sheet1": pd.read_csv(io.BytesIO(content), header=None, dtype=object)}
        else:
            frames = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, dtype=object, engine=engine)
    except Exception as e:  # noqa: BLE001
        raise ValidationFailed(f"Could not read workbook: {e}") from e

    sheets: dict[str, Any] = {}
    for name, raw in frames.items():
        raw = raw.dropna(how="all").dropna(axis=1, how="all")
        if raw.empty:
            sheets[str(name)] = {"columns": [], "rows": []}
            continue
        raw = raw.reset_index(drop=True)
        h = _find_header_row(raw)
        header_vals = raw.iloc[h].tolist() if h is not None else []
        columns: list[str] = []
        seen: dict[str, int] = {}
        for i, v in enumerate(header_vals):
            label = str(_clean(v)) if _clean(v) is not None else f"Column {i + 1}"
            if label in seen:
                seen[label] += 1
                label = f"{label} ({seen[label]})"
            else:
                seen[label] = 1
            columns.append(label)
        body = raw.iloc[(h + 1 if h is not None else 0):].head(MAX_ROWS_PER_SHEET)
        rows = []
        for _, r in body.iterrows():
            rec = {columns[i]: _clean(v) for i, v in enumerate(r.tolist()) if i < len(columns)}
            if any(v is not None for v in rec.values()):
                rows.append(rec)
        sheets[str(name)] = {"columns": columns, "rows": rows}
    if not sheets:
        raise ValidationFailed("Workbook contains no sheets")
    return sheets


def build_requirement_set(sheets: dict[str, Any]) -> RequirementSet:
    previews: list[SheetPreview] = []
    fields: list[CanonicalField] = []
    rules: list[str] = []
    warnings: list[str] = []
    used_keys: dict[str, int] = {}

    def unique_key(label: str) -> str:
        key = slugify_key(label)
        if key in used_keys:
            used_keys[key] += 1
            return f"{key}_{used_keys[key]}"
        used_keys[key] = 1
        return key

    for name, sheet in sheets.items():
        columns, rows = sheet["columns"], sheet["rows"]
        if not columns:
            previews.append(SheetPreview(name=name, columns=[], row_count=0, layout="empty"))
            continue
        roles = detect_roles(columns)
        is_note_sheet = any(hint in name.lower() for hint in NOTE_SHEET_HINTS) and "field" not in roles
        if len(columns) == 1 or (is_note_sheet and len(roles) <= 1):
            layout = "notes"
            header_text = columns[0]
            if header_text and not header_text.lower().startswith("column") and len(header_text.split()) > 3:
                rules.append(header_text)
            for r in rows:
                text = " | ".join(str(v) for v in r.values() if v is not None)
                if text:
                    rules.append(text)
        elif "field" not in roles and not rows:
            layout = "header_template"
            for i, col in enumerate(columns):
                if col.lower().startswith("column "):
                    continue
                fields.append(CanonicalField(key=unique_key(col), label=col, source_sheet=name, source_row=None))
        else:
            layout = "field_rows"
            field_col = roles.get("field")
            if field_col is None:
                # Fall back to the first column that is mostly short text.
                for col in columns:
                    vals = [r.get(col) for r in rows if r.get(col) is not None]
                    if vals and sum(isinstance(v, str) and len(v) <= 80 for v in vals) / len(vals) >= 0.8:
                        field_col = col
                        break
                if field_col is None:
                    field_col = columns[0]
                roles["field"] = field_col
                warnings.append(f"Sheet '{name}': no explicit field-name column found; using '{field_col}'.")
            extra_instruction_cols = [
                c for c in columns
                if c not in roles.values() and any(
                    re.search(rf"\b{re.escape(s)}\b", _norm(c)) for s in ROLE_SYNONYMS["instructions"])
            ]
            for idx, r in enumerate(rows, start=1):
                label = r.get(field_col)
                if label is None:
                    continue
                label = str(label).strip()
                instr_parts = [str(r[c]) for c in [roles.get("instructions"), *extra_instruction_cols]
                               if c and r.get(c) is not None]
                allowed_raw = r.get(roles["allowed_values"]) if "allowed_values" in roles else None
                allowed = [a.strip() for a in re.split(r"[,;/|\n]", str(allowed_raw)) if a.strip()] if allowed_raw else None
                raw_type = r.get(roles["data_type"]) if "data_type" in roles else None
                fields.append(CanonicalField(
                    key=unique_key(label),
                    label=label,
                    description=_str_or_none(r.get(roles["description"])) if "description" in roles else None,
                    data_type=normalize_type(raw_type),  # type: ignore[arg-type]
                    raw_type=_str_or_none(raw_type),
                    mandatory=parse_mandatory(r.get(roles["mandatory"])) if "mandatory" in roles else False,
                    instructions="; ".join(instr_parts) or None,
                    examples=_str_or_none(r.get(roles["examples"])) if "examples" in roles else None,
                    allowed_values=allowed,
                    source_sheet=name,
                    source_row=idx,
                ))
        previews.append(SheetPreview(name=name, columns=columns, row_count=len(rows), rows=rows[:PREVIEW_ROWS],
                                     detected_roles={k: v for k, v in roles.items()}, layout=layout))

    if not fields:
        raise ValidationFailed(
            "No extraction fields could be discovered in the workbook. Provide a sheet with a field-name column "
            "(e.g. 'Field Name') and one row per field, or a template sheet whose headers are the fields.",
            details={"sheets": [p.model_dump() for p in previews]},
        )
    return RequirementSet(sheets=previews, fields=fields, business_rules=rules, warnings=warnings)


def _str_or_none(v: Any) -> str | None:
    return None if v is None else str(v)


def render_requirements_text(sheets: dict[str, Any], max_chars: int = 40000) -> str:
    """Render the full workbook as markdown tables — identical input for all three models."""
    parts: list[str] = []
    for name, sheet in sheets.items():
        cols, rows = sheet["columns"], sheet["rows"]
        parts.append(f"## Sheet: {name}")
        if not cols:
            parts.append("(empty sheet)\n")
            continue
        parts.append("| " + " | ".join(_md(c) for c in cols) + " |")
        parts.append("|" + "---|" * len(cols))
        for r in rows:
            parts.append("| " + " | ".join(_md(r.get(c)) for c in cols) + " |")
        parts.append("")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Requirement workbook truncated for context length]"
    return text


def _md(v: Any) -> str:
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\n", " ")
