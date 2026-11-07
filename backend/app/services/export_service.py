"""Export generation: prompts, per-cell JSON, consolidated JSON, CSV and Excel."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.utils import utcnow
from app.db.repository import Repository
from app.schemas.requirement import RequirementSet

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def gather(repo: Repository, competition_id: str) -> dict[str, Any]:
    comp = repo.get("competitions", competition_id)
    prun = repo.get("prompt_runs", comp["prompt_run_id"])
    req = repo.get("requirements", comp["requirement_id"])
    doc = repo.get("documents", comp["document_id"])
    executions = repo.list("executions", parent_id=competition_id, order="ASC", limit=50)
    evaluation = repo.find("evaluations", f"eval_{competition_id}")
    return {"competition": comp, "prompt_run": prun, "requirement": req, "document": doc,
            "executions": executions, "evaluation": evaluation}


def prompts_export(data: dict[str, Any]) -> dict[str, Any]:
    return {"prompt_run_id": data["prompt_run"]["id"], "requirement": data["requirement"]["filename"],
            "exported_at": utcnow(),
            "prompts": [{k: p.get(k) for k in ("prompt_id", "slot", "model_id", "status", "prompt_text",
                                                "created_at", "latency_ms", "usage", "checks", "error")}
                        for p in data["prompt_run"]["prompts"]]}


def execution_export(ex: dict[str, Any]) -> dict[str, Any]:
    return {k: ex.get(k) for k in ("id", "cell", "prompt_id", "prompt_model", "extraction_model", "status",
                                    "latency_ms", "usage", "attempts", "normalized", "validation", "raw_response",
                                    "chunks", "error", "started_at", "finished_at")}


def consolidated_export(data: dict[str, Any]) -> dict[str, Any]:
    req = data["requirement"]
    return {
        "exported_at": utcnow(),
        "competition": {k: data["competition"].get(k) for k in
                        ("id", "status", "created_at", "started_at", "finished_at", "models", "extraction_models",
                         "document_name", "requirement_name", "chunk_count", "field_count")},
        "canonical_fields": req["requirement_set"]["fields"],
        "document": {k: data["document"].get(k) for k in ("filename", "page_count", "methods", "total_chars", "sha256")},
        "prompts": prompts_export(data)["prompts"],
        "executions": [execution_export(e) for e in data["executions"]],
        "evaluation": data["evaluation"],
    }


def comparison_rows(data: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    req_set = RequirementSet.model_validate(data["requirement"]["requirement_set"])
    execs = data["executions"]
    golden = (data["evaluation"] or {}).get("golden_labels") or {}
    header = ["field_key", "field_label", "data_type"] + (["golden"] if golden else []) + \
        [f"{e['prompt_id']}x{e['extraction_slot']} value" for e in execs] + \
        [f"{e['prompt_id']}x{e['extraction_slot']} status" for e in execs]
    rows = []
    for f in req_set.fields:
        vals, statuses = [], []
        for e in execs:
            nf = ((e.get("normalized") or {}).get("extracted_fields") or {}).get(f.key) or {}
            vals.append(nf.get("value"))
            fv = ((e.get("validation") or {}).get("fields") or {}).get(f.key) or {}
            statuses.append(fv.get("status") or e["status"])
        rows.append([f.key, f.label, f.data_type] + ([golden.get(f.key)] if golden else []) + vals + statuses)
    return header, rows


def csv_export(data: dict[str, Any]) -> bytes:
    header, rows = comparison_rows(data)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else v) for v in r])
    return buf.getvalue().encode("utf-8-sig")


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list[Any]]) -> None:
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append([json.dumps(v, default=str) if isinstance(v, (dict, list)) else v for v in r])
    for i, col in enumerate(header, start=1):
        width = max([len(str(col))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r) and r[i - 1] is not None])
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, width + 2))
    ws.freeze_panes = "A2"


def excel_export(data: dict[str, Any]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    comp, ev = data["competition"], data["evaluation"] or {}
    summary = [
        ["Competition", comp["id"]], ["Status", comp["status"]], ["Requirement file", comp.get("requirement_name")],
        ["Document", comp.get("document_name")], ["Golden labels", "yes" if ev.get("has_golden_labels") else "no"],
        ["Primary metric", ev.get("primary_metric_label")],
        ["Best combination", (ev.get("best_combination") or {}).get("cell")],
        ["Best prompt generator", ((ev.get("prompt_generator_ranking") or [{}])[0]).get("model_id")],
        ["Best extraction model", ((ev.get("extraction_model_ranking") or [{}])[0]).get("model_id")],
        ["Exported at", utcnow()],
    ] + [[f"Model {s}", m] for s, m in (comp.get("extraction_models") or {}).items()]
    _sheet(wb, "Summary", ["Item", "Value"], summary)

    lb_cols = ["rank", "cell", "prompt_model", "extraction_model", "status", "field_accuracy", "exact_match_accuracy",
               "supported_fill_rate", "missing_rate", "unsupported_rate", "agreement_with_majority", "json_valid",
               "latency_ms", "total_tokens"]
    _sheet(wb, "Leaderboard", lb_cols, [[c.get(k) for k in lb_cols] for c in ev.get("leaderboard") or []])
    rk_cols = ["rank", "slot", "model_id", "primary_metric", "field_accuracy", "supported_fill_rate", "missing_rate",
               "json_validity_rate", "api_failure_rate", "avg_latency_ms", "avg_total_tokens"]
    _sheet(wb, "Prompt Generator Ranking", rk_cols, [[r.get(k) for k in rk_cols] for r in ev.get("prompt_generator_ranking") or []])
    _sheet(wb, "Extraction Model Ranking", rk_cols, [[r.get(k) for k in rk_cols] for r in ev.get("extraction_model_ranking") or []])
    svc = ev.get("self_vs_cross") or {}
    sv_cols = ["cells", "primary_metric", "field_accuracy", "supported_fill_rate", "missing_rate", "avg_latency_ms", "avg_total_tokens"]
    _sheet(wb, "Self vs Cross", ["group"] + sv_cols, [[g] + [(svc.get(g) or {}).get(k) for k in sv_cols] for g in ("self", "cross")])
    header, rows = comparison_rows(data)
    _sheet(wb, "Field Comparison", header, rows)
    _sheet(wb, "Prompts", ["prompt_id", "model_id", "status", "created_at", "total_tokens", "prompt_text"],
           [[p.get("prompt_id"), p.get("model_id"), p.get("status"), p.get("created_at"),
             (p.get("usage") or {}).get("total_tokens"), p.get("prompt_text")] for p in data["prompt_run"]["prompts"]])
    _sheet(wb, "Executions", ["cell", "status", "latency_ms", "total_tokens", "attempts", "json_valid", "error"],
           [[e["cell"], e["status"], e.get("latency_ms"), (e.get("usage") or {}).get("total_tokens"), e.get("attempts"),
             (e.get("validation") or {}).get("json_valid"), e.get("error")] for e in data["executions"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
