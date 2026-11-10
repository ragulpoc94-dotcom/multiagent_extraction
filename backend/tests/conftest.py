"""Shared fixtures: synthetic requirement workbook, synthetic documents and a
deterministic mock LLM client. No network access is used anywhere in tests."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.db.repository import Repository  # noqa: E402
from app.services.groq_client import LLMError, LLMResult  # noqa: E402

DOC_LINES_P1 = [
    "SYNTHETIC CUSTOMER STATEMENT",
    "Customer Name: Asha Verma",
    "Account Number: 001234567890",
    "Statement Date: 15/03/2026",
]
DOC_LINES_P2 = [
    "Account Summary",
    "Closing Balance: INR 1,25,430.50",
    "Branch: Pune Central",
]
GOLDEN = {"customer_name": "Asha Verma", "account_number": "001234567890", "statement_date": "2026-03-15",
          "closing_balance": 125430.50, "branch_name": "Pune Central", "email_address": None}


def make_requirements_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Fields"
    ws.append(["Extraction requirements for synthetic statements"])  # title row above header
    ws.append([])
    ws.append(["Field Name", "Description", "Data Type", "Mandatory", "Extraction Instructions", "Example"])
    ws.append(["Customer Name", "Full name of the account holder", "Text", "Yes", "As printed", "John Smith"])
    ws.append(["Account Number", "Account identifier", "Text", "Y", "Keep leading zeros", "000123"])
    ws.append(["Statement Date", "Date of statement", "Date (DD/MM/YYYY)", "Yes", "Return ISO yyyy-mm-dd", None])
    ws.append(["Closing Balance", "Balance at end of period", "Amount", "Yes", "Numeric, no currency", "100.00"])
    ws.append(["Branch Name", "Servicing branch", "String", "No", None, None])
    ws.append(["Email Address", "Customer e-mail", "String", "No", "Null if absent", None])
    rules = wb.create_sheet("Business Rules")
    rules.append(["Rule"])
    rules.append(["Never infer values that are not printed on the document."])
    rules.append(["All amounts are in INR unless stated."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_digital_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for lines in (DOC_LINES_P1, DOC_LINES_P2):
        y = 780
        for line in lines:
            c.setFont("Helvetica", 13)
            c.drawString(72, y, line)
            y -= 24
        c.showPage()
    c.save()
    return buf.getvalue()


def make_scanned_png() -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1400, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except OSError:
        font = ImageFont.load_default(size=40)
    for i, line in enumerate(DOC_LINES_P1):
        d.text((40, 40 + i * 90), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FakeLLM:
    """Deterministic stand-in for Groq.

    * understanding calls -> interpretation JSON
    * prompt-generation calls -> a prompt naming the generating model
    * prompt self-assessment calls -> a confidence JSON (``bad_assessment`` models return junk)
    * extraction calls -> reads "Label: value" lines from the document text.
    Behaviour per model is configurable to simulate failures and malformed output.
    """

    def __init__(self, *, fail_models: set[str] | None = None, malformed: set[tuple[str, str]] | None = None,
                 drop_field: dict[str, str] | None = None, invent: set[str] | None = None,
                 bad_assessment: set[str] | None = None):
        self.fail_models = fail_models or set()
        self.malformed = malformed or set()  # (prompt_id, model)
        self.drop_field = drop_field or {}  # model -> key omitted
        self.invent = invent or set()  # models that hallucinate email
        self.bad_assessment = bad_assessment or set()  # models whose self-assessment is unusable
        self.calls: list[dict] = []

    async def list_models(self) -> list[str]:
        return ["model-a", "model-b", "model-c"]

    async def complete(self, model, messages, *, json_mode=False, max_tokens=None, temperature=None,
                       reasoning_effort=None):
        system, user = messages[0]["content"], messages[-1]["content"]
        self.calls.append({"model": model, "system": system, "user": user, "json_mode": json_mode,
                           "max_tokens": max_tokens, "reasoning_effort": reasoning_effort})
        if model in self.fail_models:
            raise LLMError("simulated 429 exhausted", retryable=True, status_code=429, attempts=3, kind="rate_limited")
        usage = {"prompt_tokens": len(user) // 4, "completion_tokens": 50, "total_tokens": len(user) // 4 + 50}
        if "business analyst" in system:
            keys = re.findall(r"^\| ([A-Z][A-Za-z ]+?) \|", user, re.M)
            fields = [{"name": k, "type": "string", "mandatory": True, "rules": []} for k in keys if k != "Field Name"]
            return LLMResult(json.dumps({"summary": f"{model} summary", "fields": fields,
                                         "business_rules": ["no inference"], "ambiguities": []}),
                             model, 5, 1, usage, json_mode)
        if "reviewer of extraction prompts" in system:
            if model in self.bad_assessment:
                return LLMResult("I feel good about it.", model, 3, 1, usage, json_mode)
            keys = re.search(r"in this order: (.+)", user).group(1).split(", ")
            fields = [{"key": k, "confidence": ("low" if i == 0 else "high"), "reason": "test"} for i, k in enumerate(keys)]
            fields.append({"key": "invented_field", "confidence": "high", "reason": "not in workbook"})
            return LLMResult(json.dumps({"overall_confidence": 82, "summary": f"{model} is fairly confident",
                                         "fields": fields, "assumptions": ["dates are DD/MM/YYYY"],
                                         "risks": [f"{keys[0]} may be ambiguous"]}), model, 4, 1, usage, json_mode)
        if "prompt engineer" in system:
            keys = re.search(r"refer to fields by these keys: (.+)", user).group(1)
            return LLMResult(f"You are {model}'s extractor. Extract each field atomically: {keys}. "
                             "Return null when missing. Provide evidence quotes and page numbers. Output JSON only.",
                             model, 7, 1, usage, False)
        # extraction
        prompt_id = re.search(r'prompt_generator = "(P\d)"', user).group(1)
        if (prompt_id, model) in self.malformed:
            return LLMResult('{"extracted_fields": {"customer_name": ', model, 9, 1, usage, json_mode)
        keys = re.findall(r"^- (\w+) \((\w+)", user, re.M)
        doc = user.split("=== DOCUMENT CONTENT", 1)[1]
        out = {}
        page = None
        lines = doc.splitlines()
        found: dict[str, tuple[str, int]] = {}
        for line in lines:
            m = re.match(r"=== PAGE (\d+)", line)
            if m:
                page = int(m.group(1))
                continue
            if ":" in line:
                label, val = line.split(":", 1)
                found[re.sub(r"\W+", "_", label.strip().lower())] = (val.strip(), page, line.strip())
        for key, _t in keys:
            if self.drop_field.get(model) == key:
                continue
            lookup = {"branch_name": "branch"}.get(key, key)
            if lookup in found:
                val, pg, ev = found[lookup]
                out[key] = {"value": val, "evidence": ev, "page": pg}
            elif key == "email_address" and model in self.invent:
                out[key] = {"value": "asha@example.com", "evidence": "asha@example.com", "page": 1}
            else:
                out[key] = {"value": None, "evidence": None, "page": None}
        body = {"prompt_generator": prompt_id, "extraction_model": model, "extracted_fields": out}
        return LLMResult("```json\n" + json.dumps(body) + "\n```", model, 11, 1, usage, json_mode)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(groq_api_key=SecretStr("gsk_test"), model_1="model-a", model_2="model-b", model_3="model-c",
                    data_dir=tmp_path, max_document_tokens=6000, backoff_base_seconds=0.01, requests_per_minute=1000)


@pytest.fixture
def repo(tmp_path) -> Repository:
    return Repository(tmp_path / "test.db")


@pytest.fixture
def requirements_xlsx() -> bytes:
    return make_requirements_xlsx()


@pytest.fixture
def digital_pdf() -> bytes:
    return make_digital_pdf()


@pytest.fixture
def scanned_png() -> bytes:
    return make_scanned_png()
