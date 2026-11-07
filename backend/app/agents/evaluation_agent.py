"""Evaluation & Comparison Agent.

* Accuracy metrics are computed ONLY against uploaded golden labels.
* Without golden labels, ranking uses ``supported_fill_rate`` — the measured
  share of expected fields that are non-null, type-valid and whose evidence was
  verified verbatim in the document. It is explicitly labelled as *not* accuracy.
* Cross-model agreement is reported separately and never treated as accuracy.
"""
from __future__ import annotations

import io
import json
from collections import Counter
from statistics import mean
from typing import Any

import pandas as pd

from app.agents.validation_agent import alnum, is_null, normalize_value
from app.core.config import MODEL_SLOTS
from app.core.errors import ValidationFailed
from app.core.utils import slugify_key, utcnow
from app.db.repository import Repository
from app.schemas.requirement import CanonicalField, RequirementSet

PRIMARY_WITH_GOLDEN = "field_accuracy"
PRIMARY_WITHOUT_GOLDEN = "supported_fill_rate"


# ---------------------------------------------------------------------------
# Golden labels
# ---------------------------------------------------------------------------

def parse_golden(content: bytes, filename: str, fields: list[CanonicalField]) -> tuple[dict[str, Any], list[str]]:
    """Parse golden labels from JSON / CSV / Excel into {canonical_key: value}."""
    name = filename.lower()
    pairs: dict[str, Any] = {}
    try:
        if name.endswith(".json"):
            obj = json.loads(content.decode("utf-8-sig"))
            if isinstance(obj, dict) and isinstance(obj.get("extracted_fields"), dict):
                obj = obj["extracted_fields"]
            elif isinstance(obj, dict) and isinstance(obj.get("fields"), dict):
                obj = obj["fields"]
            if not isinstance(obj, dict):
                raise ValueError("JSON must be an object mapping field -> value")
            for k, v in obj.items():
                pairs[str(k)] = v.get("value") if isinstance(v, dict) and "value" in v else v
        elif name.endswith((".csv", ".xlsx", ".xls", ".xlsm")):
            df = pd.read_csv(io.BytesIO(content), dtype=object) if name.endswith(".csv") else \
                pd.read_excel(io.BytesIO(content), dtype=object)
            cols = {c.lower().strip(): c for c in df.columns.astype(str)}
            kcol = next((cols[c] for c in ("field", "key", "field_key", "field name", "field_name", "name") if c in cols), None)
            vcol = next((cols[c] for c in ("value", "expected", "expected_value", "golden", "golden value", "label") if c in cols), None)
            if kcol and vcol:
                for _, r in df.iterrows():
                    if pd.notna(r[kcol]):
                        pairs[str(r[kcol]).strip()] = None if pd.isna(r[vcol]) else r[vcol]
            elif len(df) >= 1:  # wide format: one row, columns are fields
                row = df.iloc[0]
                for c in df.columns:
                    pairs[str(c)] = None if pd.isna(row[c]) else row[c]
        else:
            raise ValueError("Golden labels must be .json, .csv or .xlsx")
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValidationFailed(f"Could not parse golden labels: {e}") from e

    by_key = {f.key: f.key for f in fields}
    by_label = {slugify_key(f.label): f.key for f in fields}
    golden: dict[str, Any] = {}
    unknown: list[str] = []
    for k, v in pairs.items():
        ck = by_key.get(k) or by_key.get(slugify_key(k)) or by_label.get(slugify_key(k))
        if ck:
            golden[ck] = None if is_null(v) else v
        else:
            unknown.append(k)
    if not golden:
        raise ValidationFailed("Golden labels did not match any canonical field keys", details={"unknown": unknown})
    return golden, unknown


def comparable(value: Any, data_type: str) -> Any:
    if is_null(value):
        return None
    norm, err = normalize_value(value, data_type)
    if err is not None:
        return ("raw", alnum(value))
    if data_type in ("number",):
        return round(float(norm), 2)
    if data_type == "string":
        return alnum(norm)
    return norm


def strict(value: Any) -> Any:
    return None if is_null(value) else str(value).strip()


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _avg(vals: list[float | None]) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(mean(vals), 4) if vals else None


def evaluate(competition: dict[str, Any], executions: list[dict[str, Any]], req_set: RequirementSet,
             golden: dict[str, Any] | None) -> dict[str, Any]:
    fields = req_set.fields
    ftype = {f.key: f.data_type for f in fields}
    has_golden = bool(golden)
    primary = PRIMARY_WITH_GOLDEN if has_golden else PRIMARY_WITHOUT_GOLDEN

    values: dict[str, dict[str, Any]] = {}  # exec_id -> key -> raw value
    for ex in executions:
        nf = ((ex.get("normalized") or {}).get("extracted_fields") or {}) if ex["status"] == "completed" else {}
        values[ex["id"]] = {f.key: (nf.get(f.key) or {}).get("value") for f in fields}

    # ---- Agreement (consensus among completed cells; NOT accuracy) ----
    completed_ids = [ex["id"] for ex in executions if ex["status"] == "completed"]
    field_agreement: dict[str, Any] = {}
    majority: dict[str, Any] = {}
    for f in fields:
        comps = [comparable(values[i][f.key], f.data_type) for i in completed_ids]
        non_null = [c for c in comps if c is not None]
        cnt = Counter(json.dumps(c, default=str) for c in non_null)
        if cnt:
            top, top_n = cnt.most_common(1)[0]
            majority[f.key] = json.loads(top)
            if isinstance(majority[f.key], list):
                majority[f.key] = tuple(majority[f.key])
        field_agreement[f.key] = {
            "distinct_values": len(cnt),
            "non_null_count": len(non_null),
            "null_count": len(comps) - len(non_null),
            "majority_share": _rate(cnt.most_common(1)[0][1], len(comps)) if cnt else None,
            "unanimous": len(comps) > 0 and len(cnt) <= 1 and (len(non_null) in (0, len(comps))),
        }

    # ---- Per-combination metrics ----
    combos: list[dict[str, Any]] = []
    for ex in executions:
        v = ex.get("validation") or {}
        completed = ex["status"] == "completed"
        usage = ex.get("usage") or {}
        m: dict[str, Any] = {
            "execution_id": ex["id"], "cell": ex["cell"], "prompt_slot": ex["prompt_slot"],
            "prompt_id": ex["prompt_id"], "prompt_model": ex.get("prompt_model"),
            "extraction_slot": ex["extraction_slot"], "extraction_model": ex["extraction_model"],
            "is_self_prompt": ex["is_self_prompt"], "status": ex["status"],
            "api_failure": ex["status"] == "failed",
            "json_valid": bool(v.get("json_valid")) if completed else False,
            "schema_valid": bool(v.get("schema_valid")) if completed else False,
            "latency_ms": ex.get("latency_ms"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "missing_rate": v.get("missing_rate") if completed else None,
            "unsupported_rate": _rate(v.get("unsupported", 0), v.get("fields_expected", 0)) if completed else None,
            "type_error_rate": _rate(v.get("type_errors", 0), v.get("fields_expected", 0)) if completed else None,
            "supported_fill_rate": v.get("supported_fill_rate") if completed else (0.0 if ex["status"] == "failed" else None),
        }
        # Agreement with majority (only fields where a majority exists)
        if completed and majority:
            agree = [comparable(values[ex["id"]][k], ftype[k]) == mv for k, mv in majority.items()]
            m["agreement_with_majority"] = _rate(sum(agree), len(agree))
        else:
            m["agreement_with_majority"] = None
        if has_golden:
            keys = list(golden.keys())
            correct = exact = incorrect = 0
            per_field: dict[str, Any] = {}
            for k in keys:
                pred = values[ex["id"]].get(k) if completed else None
                g = golden[k]
                ok = comparable(pred, ftype[k]) == comparable(g, ftype[k])
                ex_ok = strict(pred) == strict(g)
                correct += ok
                exact += ex_ok
                if not ok and not is_null(pred):
                    incorrect += 1
                per_field[k] = {"predicted": pred, "golden": g, "correct": ok, "exact": ex_ok}
            m.update({
                "field_accuracy": _rate(correct, len(keys)),
                "exact_match_accuracy": _rate(exact, len(keys)),
                "incorrect_rate": _rate(incorrect, len(keys)),
                "all_fields_correct": correct == len(keys),
                "golden_field_results": per_field,
            })
        combos.append(m)

    def score(c: dict[str, Any]) -> float:
        s = c.get(primary)
        if s is None:
            return -1.0
        return s

    leaderboard = sorted(
        combos,
        key=lambda c: (-score(c), c.get("missing_rate") if c.get("missing_rate") is not None else 9,
                       c.get("latency_ms") or 10**9),
    )
    for rank, c in enumerate(leaderboard, start=1):
        c["rank"] = rank

    def group(slot_key: str) -> list[dict[str, Any]]:
        out = []
        for slot in MODEL_SLOTS:
            rows = [c for c in combos if c[slot_key] == slot]
            if not rows:
                continue
            model = rows[0]["prompt_model" if slot_key == "prompt_slot" else "extraction_model"]
            out.append({
                "slot": slot, "model_id": model, "cells": len(rows),
                "primary_metric": _avg([score(r) if score(r) >= 0 else None for r in rows]),
                "field_accuracy": _avg([r.get("field_accuracy") for r in rows]) if has_golden else None,
                "exact_match_accuracy": _avg([r.get("exact_match_accuracy") for r in rows]) if has_golden else None,
                "supported_fill_rate": _avg([r.get("supported_fill_rate") for r in rows]),
                "missing_rate": _avg([r.get("missing_rate") for r in rows]),
                "json_validity_rate": _rate(sum(r["json_valid"] for r in rows), len(rows)),
                "api_failure_rate": _rate(sum(r["api_failure"] for r in rows), len(rows)),
                "avg_latency_ms": _avg([r.get("latency_ms") for r in rows]),
                "avg_total_tokens": _avg([r.get("total_tokens") for r in rows]),
            })
        out.sort(key=lambda r: -(r["primary_metric"] if r["primary_metric"] is not None else -1))
        for i, r in enumerate(out, start=1):
            r["rank"] = i
        return out

    def subset(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "cells": len(rows),
            "primary_metric": _avg([score(r) if score(r) >= 0 else None for r in rows]),
            "field_accuracy": _avg([r.get("field_accuracy") for r in rows]) if has_golden else None,
            "supported_fill_rate": _avg([r.get("supported_fill_rate") for r in rows]),
            "missing_rate": _avg([r.get("missing_rate") for r in rows]),
            "avg_latency_ms": _avg([r.get("latency_ms") for r in rows]),
            "avg_total_tokens": _avg([r.get("total_tokens") for r in rows]),
        }

    heatmap = [[next((score(c) if score(c) >= 0 else None for c in combos
                      if c["prompt_slot"] == g and c["extraction_slot"] == e), None)
                for e in MODEL_SLOTS] for g in MODEL_SLOTS]
    scored = [c for c in leaderboard if score(c) >= 0]
    best = scored[0] if scored else None

    return {
        "competition_id": competition["id"],
        "has_golden_labels": has_golden,
        "primary_metric": primary,
        "primary_metric_label": "Field accuracy (vs golden labels)" if has_golden else
        "Supported fill rate (non-null, type-valid, evidence verified in document — NOT accuracy)",
        "notes": [
            "Agreement between models is consensus, not proof of correctness.",
            "Failed executions count as 0 for supported_fill_rate; skipped cells are excluded.",
        ] + ([] if has_golden else ["Upload golden labels to compute field and exact-match accuracy."]),
        "golden_field_count": len(golden) if golden else 0,
        "combinations": combos,
        "leaderboard": [{k: c[k] for k in c if k != "golden_field_results"} for c in leaderboard],
        "prompt_generator_ranking": group("prompt_slot"),
        "extraction_model_ranking": group("extraction_slot"),
        "best_combination": {k: best[k] for k in best if k != "golden_field_results"} if best else None,
        "self_vs_cross": {
            "self": subset([c for c in combos if c["is_self_prompt"]]),
            "cross": subset([c for c in combos if not c["is_self_prompt"]]),
        },
        "heatmap": {"rows": list(MODEL_SLOTS), "cols": list(MODEL_SLOTS), "metric": primary, "values": heatmap},
        "field_agreement": field_agreement,
        "evaluated_at": utcnow(),
    }


def run_evaluation(repo: Repository, competition_id: str, golden_upload: tuple[bytes, str] | None = None,
                   *, keep_existing_golden: bool = True) -> dict[str, Any]:
    comp = repo.get("competitions", competition_id)
    req = repo.get("requirements", comp["requirement_id"])
    req_set = RequirementSet.model_validate(req["requirement_set"])
    eval_id = f"eval_{competition_id}"
    existing = repo.find("evaluations", eval_id)
    golden, unknown = None, []
    if golden_upload:
        golden, unknown = parse_golden(golden_upload[0], golden_upload[1], req_set.fields)
    elif keep_existing_golden and existing:
        golden = existing.get("golden_labels")
    executions = repo.list("executions", parent_id=competition_id, order="ASC", limit=50)
    report = evaluate(comp, executions, req_set, golden)
    report["golden_labels"] = golden
    report["golden_unknown_keys"] = unknown
    if existing:
        return repo.update("evaluations", eval_id, {**report, "status": "completed"})
    return repo.insert("evaluations", eval_id, report, parent_id=competition_id, status="completed")
