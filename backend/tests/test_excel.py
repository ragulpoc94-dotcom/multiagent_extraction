import io

import pytest
from openpyxl import Workbook

from app.core.errors import ValidationFailed
from app.services import excel_service as xs


def _xlsx(build) -> bytes:
    wb = Workbook()
    build(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_discovers_fields_roles_and_rules(requirements_xlsx):
    sheets = xs.read_workbook(requirements_xlsx, "req.xlsx")
    rs = xs.build_requirement_set(sheets)
    keys = rs.field_keys()
    assert keys == ["customer_name", "account_number", "statement_date", "closing_balance", "branch_name",
                    "email_address"]
    by = {f.key: f for f in rs.fields}
    assert by["statement_date"].data_type == "date"
    assert by["closing_balance"].data_type == "number"
    assert by["customer_name"].mandatory and not by["branch_name"].mandatory
    assert by["account_number"].instructions == "Keep leading zeros"
    assert by["customer_name"].examples == "John Smith"
    fields_sheet = next(s for s in rs.sheets if s.name == "Fields")
    assert fields_sheet.detected_roles["field"] == "Field Name"
    assert fields_sheet.detected_roles["data_type"] == "Data Type"
    assert any("infer" in r for r in rs.business_rules)


def test_header_row_detected_below_title(requirements_xlsx):
    sheets = xs.read_workbook(requirements_xlsx, "req.xlsx")
    assert sheets["Fields"]["columns"][0] == "Field Name"


def test_header_template_layout_fields_are_columns():
    data = _xlsx(lambda wb: wb.active.append(["Invoice No", "Invoice Date", "Total Amount", "Vendor"]))
    rs = xs.build_requirement_set(xs.read_workbook(data, "t.xlsx"))
    assert rs.field_keys() == ["invoice_no", "invoice_date", "total_amount", "vendor"]
    assert rs.sheets[0].layout == "header_template"


def test_unusual_headers_and_duplicates_get_unique_keys():
    def build(wb):
        ws = wb.active
        ws.append(["Attribute", "Definition", "Format", "Required?"])
        ws.append(["Party Name", "x", "text", "mandatory"])
        ws.append(["Party Name", "y", "integer", "optional"])
    rs = xs.build_requirement_set(xs.read_workbook(_xlsx(build), "t.xlsx"))
    assert rs.field_keys() == ["party_name", "party_name_2"]
    assert rs.fields[1].data_type == "integer"
    assert rs.fields[0].mandatory is True and rs.fields[1].mandatory is False


def test_empty_workbook_raises():
    with pytest.raises(ValidationFailed):
        xs.build_requirement_set(xs.read_workbook(_xlsx(lambda wb: None), "t.xlsx"))


def test_corrupt_file_raises():
    with pytest.raises(ValidationFailed):
        xs.read_workbook(b"not an excel file", "bad.xlsx")


@pytest.mark.parametrize("raw,expected", [("Date (DD/MM/YYYY)", "date"), ("Amount", "number"), ("Integer", "integer"),
                                          ("Y/N", "boolean"), ("Alphanumeric", "string"), (None, "string")])
def test_type_normalization(raw, expected):
    assert xs.normalize_type(raw) == expected


def test_render_is_identical_markdown(requirements_xlsx):
    sheets = xs.read_workbook(requirements_xlsx, "req.xlsx")
    a = xs.render_requirements_text(sheets)
    b = xs.render_requirements_text(sheets)
    assert a == b and "## Sheet: Fields" in a and "| Customer Name |" in a
