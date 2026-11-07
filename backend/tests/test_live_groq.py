"""Real Groq inference (opt-in): `pytest -m live`.

Runs the complete N² pipeline against the three configured models using the
synthetic workbook and PDF. Skipped unless GROQ_API_KEY and MODEL_1..3 are set.
"""
import asyncio
import json

import pytest

from app.agents import document_agent, evaluation_agent, extraction_agent, prompt_agent, requirement_agent
from app.core.config import Settings
from app.db.repository import Repository
from app.services.groq_client import GroqLLMClient
from tests.conftest import GOLDEN, make_digital_pdf, make_requirements_xlsx

pytestmark = pytest.mark.live


@pytest.fixture
def live_settings(tmp_path):
    s = Settings.from_env()
    if s.missing_configuration():
        pytest.skip(f"live config missing: {s.missing_configuration()}")
    return s.model_copy(update={"data_dir": tmp_path})


def test_live_models_available(live_settings):
    client = GroqLLMClient(live_settings)
    available = set(asyncio.run(client.list_models()))
    missing = [m for m in live_settings.models.values() if m not in available]
    assert not missing, f"Models not available on this Groq account: {missing}"


def test_live_full_n2_pipeline(live_settings, tmp_path):
    repo = Repository(tmp_path / "live.db")

    async def go():
        client = GroqLLMClient(live_settings)
        req = requirement_agent.ingest(repo, make_requirements_xlsx(), "req.xlsx")
        await requirement_agent.understand(repo, client, live_settings, req["id"])
        prun = await prompt_agent.generate(repo, client, live_settings, req["id"])
        doc = document_agent.save_upload(repo, live_settings, make_digital_pdf(), "synthetic.pdf")
        await document_agent.process(repo, live_settings, doc["id"])
        comp = extraction_agent.create_competition(repo, live_settings, prompt_run_id=prun["id"], document_id=doc["id"])
        await extraction_agent.run_competition(repo, client, live_settings, comp["id"])
        return prun, comp

    prun, comp = asyncio.run(go())
    ev = evaluation_agent.run_evaluation(repo, comp["id"], (json.dumps(GOLDEN).encode(), "golden.json"))
    execs = repo.list("executions", parent_id=comp["id"])
    print("\nPrompt generation:", [(p["prompt_id"], p["model_id"], p["status"]) for p in prun["prompts"]])
    for c in ev["leaderboard"]:
        print(f"{c['rank']:>2} {c['cell']:<7} acc={c.get('field_accuracy')} json={c['json_valid']} "
              f"lat={c['latency_ms']}ms tok={c['total_tokens']} status={c['status']}")
    assert len(execs) == 9
    assert all(e["status"] in ("completed", "failed", "skipped") for e in execs)
    assert sum(e["status"] == "completed" for e in execs) >= 1
