"""End-to-end pipeline tests with synthetic documents and a mocked Groq client:
requirements -> 3 interpretations -> 3 prompts -> document -> 9 executions ->
validation -> evaluation -> exports."""
import asyncio
import io
import json

import pytest
from openpyxl import load_workbook

from app.agents import document_agent, evaluation_agent, extraction_agent, prompt_agent, requirement_agent
from app.core.errors import ConfigurationError
from app.jobs.runner import JobRunner
from app.services import export_service
from tests.conftest import GOLDEN, FakeLLM


def run(c):
    return asyncio.run(c)


def setup_pipeline(repo, settings, xlsx, pdf, llm, chunk_per_page=False):
    req = requirement_agent.ingest(repo, xlsx, "req.xlsx")
    run(requirement_agent.understand(repo, llm, settings, req["id"]))
    prun = run(prompt_agent.generate(repo, llm, settings, req["id"]))
    doc = document_agent.save_upload(repo, settings, pdf, "statement.pdf")
    processed = run(document_agent.process(repo, settings, doc["id"]))
    if chunk_per_page:  # budget fits the largest page but not two pages together
        largest = max(len(document_agent.page_block(p)) for p in processed["pages"])
        settings.max_document_tokens = largest // 4 + 2
    comp = extraction_agent.create_competition(repo, settings, prompt_run_id=prun["id"], document_id=doc["id"])
    return req, prun, doc, comp


def test_three_independent_interpretations(repo, settings, requirements_xlsx):
    llm = FakeLLM()
    req = requirement_agent.ingest(repo, requirements_xlsx, "req.xlsx")
    out = run(requirement_agent.understand(repo, llm, settings, req["id"]))
    interps = out["interpretations"]
    assert [i["slot"] for i in interps] == ["M1", "M2", "M3"]
    assert {i["model_id"] for i in interps} == {"model-a", "model-b", "model-c"}
    assert all(i["status"] == "completed" and i["coverage"] == 1.0 for i in interps)
    # Equivalent requirement content sent to all three models
    users = [c["user"] for c in llm.calls]
    assert len(set(users)) == 1


def test_three_prompts_generated_and_stored(repo, settings, requirements_xlsx):
    llm = FakeLLM()
    req = requirement_agent.ingest(repo, requirements_xlsx, "req.xlsx")
    prun = run(prompt_agent.generate(repo, llm, settings, req["id"]))
    assert prun["status"] == "completed"
    ps = prun["prompts"]
    assert [p["prompt_id"] for p in ps] == ["P1", "P2", "P3"]
    assert len({p["prompt_text"] for p in ps}) == 3
    assert all(p["created_at"] and p["model_id"] and p["checks"]["field_key_coverage"] == 1.0 for p in ps)
    assert repo.get("prompt_runs", prun["id"])["prompts"][0]["prompt_text"] == ps[0]["prompt_text"]


def test_missing_configuration_is_explicit(repo, settings, requirements_xlsx):
    settings.groq_api_key = None
    req = requirement_agent.ingest(repo, requirements_xlsx, "req.xlsx")
    with pytest.raises(ConfigurationError) as ei:
        run(prompt_agent.generate(repo, FakeLLM(), settings, req["id"]))
    assert "GROQ_API_KEY" in ei.value.details["missing"]


def test_all_nine_combinations_execute_independently(repo, settings, requirements_xlsx, digital_pdf):
    llm = FakeLLM()
    _req, prun, _doc, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, llm)
    llm.calls.clear()
    final = run(extraction_agent.run_competition(repo, llm, settings, comp["id"]))
    assert final["status"] == "completed"
    execs = repo.list("executions", parent_id=comp["id"], order="ASC")
    assert len(execs) == 9
    assert {(e["prompt_slot"], e["extraction_slot"]) for e in execs} == {(g, x) for g in ("M1", "M2", "M3")
                                                                            for x in ("M1", "M2", "M3")}
    assert sum(e["is_self_prompt"] for e in execs) == 3
    assert len(llm.calls) == 9
    prompts = {p["prompt_id"]: p["prompt_text"] for p in prun["prompts"]}
    user_payloads = set()
    for call in llm.calls:
        # system message is the generated prompt, byte-for-byte unchanged
        assert call["system"] in prompts.values()
        assert call["json_mode"] is True
        # no cell sees another cell's output
        assert "extracted_fields\": {\"" not in call["user"]
        user_payloads.add(call["user"].split("=== ORIGINAL REQUIREMENT WORKBOOK ===")[1])
    assert len(user_payloads) == 1  # same requirements + document for every cell
    for e in execs:
        assert e["status"] == "completed" and e["validation"]["json_valid"]
        assert e["usage"]["total_tokens"] > 0 and e["latency_ms"] is not None and e["raw_response"]
        assert e["validation"]["fields"]["customer_name"]["status"] == "ok"
        assert e["validation"]["fields"]["email_address"]["status"] == "missing"


def test_failures_and_malformed_outputs_are_recorded(repo, settings, requirements_xlsx, digital_pdf):
    _req, _prun, _doc, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, FakeLLM())
    llm = FakeLLM(fail_models={"model-c"}, malformed={("P1", "model-b")}, invent={"model-a"})
    final = run(extraction_agent.run_competition(repo, llm, settings, comp["id"]))
    assert final["status"] == "completed_with_errors"
    execs = {e["cell"]: e for e in repo.list("executions", parent_id=comp["id"])}
    assert all(execs[f"P{i}×M3"]["status"] == "failed" for i in (1, 2, 3))
    assert "rate_limited" in execs["P1×M3"]["error"]
    bad = execs["P1×M2"]
    assert bad["status"] == "completed" and not bad["validation"]["json_valid"] and bad["raw_response"]
    assert execs["P2×M1"]["validation"]["fields"]["email_address"]["status"] == "unsupported"


def test_failed_prompt_generation_skips_its_row(repo, settings, requirements_xlsx, digital_pdf):
    req = requirement_agent.ingest(repo, requirements_xlsx, "req.xlsx")
    prun = run(prompt_agent.generate(repo, FakeLLM(fail_models={"model-b"}), settings, req["id"]))
    assert prun["status"] == "partial"
    doc = document_agent.save_upload(repo, settings, digital_pdf, "s.pdf")
    run(document_agent.process(repo, settings, doc["id"]))
    comp = extraction_agent.create_competition(repo, settings, prompt_run_id=prun["id"], document_id=doc["id"])
    run(extraction_agent.run_competition(repo, FakeLLM(), settings, comp["id"]))
    execs = repo.list("executions", parent_id=comp["id"])
    skipped = [e for e in execs if e["status"] == "skipped"]
    assert len(skipped) == 3 and all(e["prompt_slot"] == "M2" for e in skipped)


def test_chunked_document_merges_across_pages(repo, settings, requirements_xlsx, digital_pdf):
    llm = FakeLLM()
    _req, _prun, _doc, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, llm, chunk_per_page=True)
    assert comp["chunk_count"] == 2
    llm.calls.clear()
    run(extraction_agent.run_competition(repo, llm, settings, comp["id"]))
    assert len(llm.calls) == 18
    e = repo.list("executions", parent_id=comp["id"])[0]
    fields = e["normalized"]["extracted_fields"]
    assert fields["customer_name"]["page"] == 1 and fields["closing_balance"]["page"] == 2
    assert len(e["chunks"]) == 2


def test_evaluation_without_golden_does_not_claim_accuracy(repo, settings, requirements_xlsx, digital_pdf):
    _r, _p, _d, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, FakeLLM())
    run(extraction_agent.run_competition(repo, FakeLLM(drop_field={"model-b": "branch_name"}), settings, comp["id"]))
    ev = evaluation_agent.run_evaluation(repo, comp["id"])
    assert ev["has_golden_labels"] is False and ev["primary_metric"] == "supported_fill_rate"
    assert all("field_accuracy" not in c for c in ev["combinations"])
    assert len(ev["leaderboard"]) == 9
    ext = {r["slot"]: r for r in ev["extraction_model_ranking"]}
    assert ext["M2"]["supported_fill_rate"] < ext["M1"]["supported_fill_rate"]
    assert ev["extraction_model_ranking"][-1]["slot"] == "M2"
    assert ev["self_vs_cross"]["self"]["cells"] == 3 and ev["self_vs_cross"]["cross"]["cells"] == 6
    assert ev["field_agreement"]["customer_name"]["unanimous"] is True
    assert ev["field_agreement"]["branch_name"]["null_count"] == 3


def test_evaluation_with_golden_labels(repo, settings, requirements_xlsx, digital_pdf):
    _r, _p, _d, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, FakeLLM())
    run(extraction_agent.run_competition(repo, FakeLLM(invent={"model-c"}), settings, comp["id"]))
    golden = json.dumps(GOLDEN).encode()
    ev = evaluation_agent.run_evaluation(repo, comp["id"], (golden, "golden.json"))
    assert ev["has_golden_labels"] and ev["primary_metric"] == "field_accuracy"
    combos = {c["cell"]: c for c in ev["combinations"]}
    assert combos["P1×M1"]["field_accuracy"] == 1.0
    # strict exact-match differs (date/amount formatting) from normalised accuracy
    assert combos["P1×M1"]["exact_match_accuracy"] < 1.0
    assert combos["P1×M3"]["field_accuracy"] == pytest.approx(5 / 6, abs=1e-3)
    assert combos["P1×M3"]["incorrect_rate"] == pytest.approx(1 / 6, abs=1e-3)
    assert ev["extraction_model_ranking"][-1]["slot"] == "M3"
    assert ev["best_combination"]["extraction_slot"] != "M3"
    assert ev["heatmap"]["values"][0][2] == pytest.approx(5 / 6, abs=1e-3)
    # golden persists on re-evaluation without upload
    again = evaluation_agent.run_evaluation(repo, comp["id"])
    assert again["has_golden_labels"]


def test_golden_csv_and_label_matching(repo, settings, requirements_xlsx, digital_pdf):
    _r, _p, _d, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, FakeLLM())
    run(extraction_agent.run_competition(repo, FakeLLM(), settings, comp["id"]))
    csv = b"field,value\nCustomer Name,Asha Verma\nUnknown Thing,1\n"
    ev = evaluation_agent.run_evaluation(repo, comp["id"], (csv, "g.csv"))
    assert ev["golden_field_count"] == 1 and ev["golden_unknown_keys"] == ["Unknown Thing"]


def test_exports(repo, settings, requirements_xlsx, digital_pdf):
    _r, _p, _d, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, FakeLLM())
    run(extraction_agent.run_competition(repo, FakeLLM(), settings, comp["id"]))
    evaluation_agent.run_evaluation(repo, comp["id"], (json.dumps(GOLDEN).encode(), "g.json"))
    data = export_service.gather(repo, comp["id"])
    cons = export_service.consolidated_export(data)
    assert len(cons["executions"]) == 9 and len(cons["prompts"]) == 3
    csv_text = export_service.csv_export(data).decode("utf-8-sig")
    assert csv_text.splitlines()[0].startswith("field_key,field_label,data_type,golden")
    assert len(csv_text.strip().splitlines()) == 1 + 6
    header, rows = export_service.comparison_rows(data)
    correct_cols = [i for i, h in enumerate(header) if h.endswith(" correct")]
    assert len(correct_cols) == 9 and not any(h.endswith(" status") for h in header)
    assert all(r[i] in (True, False, None) for r in rows for i in correct_cols)
    assert any(r[i] is True for r in rows for i in correct_cols)
    assert "TRUE" in csv_text and ",ok" not in csv_text
    wb = load_workbook(io.BytesIO(export_service.excel_export(data)))
    assert {"Summary", "Leaderboard", "Prompt Generator Ranking", "Extraction Model Ranking", "Self vs Cross",
            "Field Comparison", "Prompts", "Executions"} <= set(wb.sheetnames)
    assert wb["Leaderboard"].max_row == 10


def test_restart_recovery_and_resume(repo, settings, requirements_xlsx, digital_pdf):
    _r, _p, _d, comp = setup_pipeline(repo, settings, requirements_xlsx, digital_pdf, FakeLLM())
    # simulate a crash mid-run
    repo.update("competitions", comp["id"], {"status": "running"})
    first = repo.list("executions", parent_id=comp["id"], order="ASC")[0]
    repo.update("executions", first["id"], {"status": "running"})
    runner = JobRunner(repo, FakeLLM(), settings)
    assert runner.recover_on_startup() == 1
    assert repo.get("competitions", comp["id"])["status"] == "interrupted"
    assert repo.get("executions", first["id"])["status"] == "interrupted"

    async def resume():
        task = runner.start(comp["id"], only_unfinished=True)
        await task
    run(resume())
    assert repo.get("competitions", comp["id"])["status"] == "completed"
    assert repo.find("evaluations", f"eval_{comp['id']}") is not None  # auto-evaluated
