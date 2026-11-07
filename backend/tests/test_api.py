"""API endpoint tests (FastAPI TestClient + mocked Groq). Full workflow through HTTP."""
import json
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.conftest import GOLDEN, FakeLLM  # noqa: E402


@pytest.fixture
def client(settings, repo):
    app = create_app(settings=settings, client=FakeLLM(), repo=repo)
    with TestClient(app) as c:
        yield c


def test_health_and_models(client):
    h = client.get("/api/v1/health").json()
    assert h["success"] and h["data"]["status"] == "ok" and h["data"]["configuration_missing"] == []
    m = client.get("/api/v1/models").json()["data"]
    assert m["api_key_configured"] and [x["model_id"] for x in m["models"]] == ["model-a", "model-b", "model-c"]
    assert "gsk_test" not in json.dumps(m)
    v = client.get("/api/v1/models/verify").json()["data"]
    assert v["verified"] is True


def test_error_envelope(client):
    r = client.get("/api/v1/requirements/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/v1/requirements/upload", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and not r.json()["success"]
    r = client.post("/api/v1/prompts/generate", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "request_invalid"


def test_full_workflow_over_http(client, requirements_xlsx, digital_pdf):
    r = client.post("/api/v1/requirements/upload",
                    files={"file": ("req.xlsx", requirements_xlsx, "application/octet-stream")})
    assert r.status_code == 201
    req = r.json()["data"]
    assert len(req["requirement_set"]["fields"]) == 6 and "sheets_raw" not in req

    und = client.post(f"/api/v1/requirements/{req['id']}/understand").json()["data"]
    assert len(und["interpretations"]) == 3

    prun = client.post("/api/v1/prompts/generate", json={"requirement_id": req["id"]}).json()["data"]
    assert len(prun["prompts"]) == 3
    assert client.get(f"/api/v1/prompts/{prun['id']}").json()["data"]["id"] == prun["id"]

    doc = client.post("/api/v1/documents/upload", files={"file": ("s.pdf", digital_pdf, "application/pdf")}).json()["data"]
    assert "path" not in doc
    doc = client.post(f"/api/v1/documents/{doc['id']}/process").json()["data"]
    assert doc["status"] == "processed" and doc["page_count"] == 2
    img = client.get(f"/api/v1/documents/{doc['id']}/pages/1/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"

    comp = client.post("/api/v1/competitions", json={"prompt_run_id": prun["id"], "document_id": doc["id"]}).json()["data"]
    cid = comp["id"]
    for _ in range(100):
        st = client.get(f"/api/v1/competitions/{cid}/status").json()["data"]
        if st["status"] not in ("queued", "running") and not st["is_running"]:
            break
        time.sleep(0.05)
    assert st["status"] == "completed" and len(st["cells"]) == 9
    assert all(c["json_valid"] for c in st["cells"])

    res = client.get(f"/api/v1/competitions/{cid}/results").json()["data"]
    assert len(res["executions"]) == 9 and len(res["fields"]) == 6
    eid = res["executions"][0]["id"]
    assert client.get(f"/api/v1/competitions/{cid}/executions/{eid}").json()["data"]["raw_response"]

    # auto-evaluation exists; then upload golden labels
    assert client.get(f"/api/v1/evaluations/{cid}").json()["data"]["has_golden_labels"] is False
    ev = client.post(f"/api/v1/evaluations/{cid}",
                     files={"golden": ("g.json", json.dumps(GOLDEN).encode(), "application/json")}).json()["data"]
    assert ev["has_golden_labels"] and ev["best_combination"]["field_accuracy"] == 1.0

    for kind, ctype in (("consolidated", "application/json"), ("prompts", "application/json"), ("csv", "text/csv"),
                        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")):
        r = client.get(f"/api/v1/exports/{cid}", params={"kind": kind})
        assert r.status_code == 200 and r.headers["content-type"].startswith(ctype)
        assert "attachment" in r.headers["content-disposition"]
    r = client.get(f"/api/v1/exports/{cid}", params={"kind": "execution", "execution_id": eid})
    assert r.status_code == 200 and json.loads(r.content)["id"] == eid

    ov = client.get("/api/v1/overview").json()["data"]
    assert ov["counts"]["competitions"] == 1 and ov["recent_competitions"][0]["completed_cells"] == 9


def test_competition_requires_processed_document(client, requirements_xlsx, digital_pdf):
    req = client.post("/api/v1/requirements/upload", files={"file": ("r.xlsx", requirements_xlsx, "x")}).json()["data"]
    prun = client.post("/api/v1/prompts/generate", json={"requirement_id": req["id"]}).json()["data"]
    doc = client.post("/api/v1/documents/upload", files={"file": ("s.pdf", digital_pdf, "application/pdf")}).json()["data"]
    r = client.post("/api/v1/competitions", json={"prompt_run_id": prun["id"], "document_id": doc["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
