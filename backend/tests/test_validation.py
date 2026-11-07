import json

import pytest

from app.agents.validation_agent import normalize_value, parse_number, validate_extraction
from app.schemas.requirement import CanonicalField

FIELDS = [
    CanonicalField(key="name", label="Name", source_sheet="s"),
    CanonicalField(key="amount", label="Amount", data_type="number", source_sheet="s"),
    CanonicalField(key="dt", label="Date", data_type="date", source_sheet="s"),
    CanonicalField(key="email", label="Email", source_sheet="s"),
]
PAGES = [{"page": 1, "text": "Name: Asha Verma\nDate: 15/03/2026"}, {"page": 2, "text": "Amount: INR 1,25,430.50"}]


def out(**fields):
    return json.dumps({"prompt_generator": "P1", "extraction_model": "m", "extracted_fields": fields})


def test_fully_valid_output():
    raw = out(name={"value": "Asha Verma", "evidence": "Name: Asha Verma", "page": 1},
              amount={"value": "INR 1,25,430.50", "evidence": "INR 1,25,430.50", "page": 2},
              dt={"value": "15/03/2026", "evidence": "15/03/2026", "page": 1},
              email={"value": None, "evidence": None, "page": None})
    rep, norm = validate_extraction(raw, FIELDS, PAGES)
    assert rep.json_valid and rep.schema_valid
    assert rep.fields["amount"].normalized_value == 125430.50
    assert rep.fields["dt"].normalized_value == "2026-03-15"
    assert rep.missing == 1 and rep.supported_fill_rate == 0.75 and rep.missing_rate == 0.25
    assert norm["extracted_fields"]["email"]["value"] is None


def test_malformed_json_is_invalid_and_not_repaired():
    rep, norm = validate_extraction('{"extracted_fields": {"name": ', FIELDS, PAGES)
    assert not rep.json_valid and norm is None and rep.not_returned == 4 and rep.parse_error


def test_hallucinated_value_flagged_unsupported():
    raw = out(name={"value": "Asha Verma", "evidence": "Asha Verma", "page": 1},
              email={"value": "asha@example.com", "evidence": "asha@example.com", "page": 1})
    rep, _ = validate_extraction(raw, FIELDS, PAGES)
    assert rep.fields["email"].status == "unsupported"
    assert rep.fields["amount"].status == "not_returned"
    assert rep.unexpected_keys == []


def test_type_error_and_page_out_of_range_and_wrong_page():
    raw = out(amount={"value": "about a lakh", "evidence": "Amount", "page": 2},
              name={"value": "Asha Verma", "evidence": "Asha Verma", "page": 9},
              dt={"value": "15/03/2026", "evidence": "15/03/2026", "page": 2})
    rep, _ = validate_extraction(raw, FIELDS, PAGES)
    assert rep.fields["amount"].status == "type_error"
    assert rep.fields["name"].status == "page_invalid"
    assert rep.fields["dt"].status == "ok" and any("different page" in i for i in rep.fields["dt"].issues)


def test_flat_scalar_output_accepted_but_flagged():
    rep, _ = validate_extraction(json.dumps({"name": "Asha Verma", "unknown_key": 1}), FIELDS, PAGES)
    assert rep.fields["name"].status == "unsupported"
    assert any("bare value" in i for i in rep.fields["name"].issues)
    assert rep.unexpected_keys == ["unknown_key"]


def test_null_like_strings_are_missing():
    rep, _ = validate_extraction(out(name={"value": "N/A", "evidence": None, "page": None}), FIELDS, PAGES)
    assert rep.fields["name"].status == "missing"


@pytest.mark.parametrize("raw,exp", [("1,234.50", 1234.5), ("1.234,50", 1234.5), ("$ 99", 99.0), ("(12)", -12.0),
                                     ("12,5", 12.5), ("abc", None), (True, None)])
def test_parse_number(raw, exp):
    assert parse_number(raw) == exp


def test_normalize_integer_and_bool():
    assert normalize_value("42", "integer") == (42, None)
    assert normalize_value("4.2", "integer")[1] is not None
    assert normalize_value("Yes", "boolean") == (True, None)
