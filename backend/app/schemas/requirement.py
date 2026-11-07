"""Requirement (Excel) schemas. Nothing here knows about banking fields:
the canonical schema is derived entirely from the uploaded workbook."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CanonicalType = Literal["string", "number", "integer", "date", "boolean"]


class SheetPreview(BaseModel):
    name: str
    columns: list[str]
    row_count: int
    rows: list[dict[str, Any]] = Field(default_factory=list, description="Preview rows (capped)")
    detected_roles: dict[str, str] = Field(default_factory=dict, description="role -> column name")
    layout: Literal["field_rows", "header_template", "notes", "empty"] = "field_rows"


class CanonicalField(BaseModel):
    key: str
    label: str
    description: str | None = None
    data_type: CanonicalType = "string"
    raw_type: str | None = None
    mandatory: bool = False
    instructions: str | None = None
    examples: str | None = None
    allowed_values: list[str] | None = None
    source_sheet: str
    source_row: int | None = None


class RequirementSet(BaseModel):
    sheets: list[SheetPreview]
    fields: list[CanonicalField]
    business_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def field_keys(self) -> list[str]:
        return [f.key for f in self.fields]


class InterpretedField(BaseModel):
    key: str | None = None
    name: str | None = None
    description: str | None = None
    type: str | None = None
    mandatory: bool | None = None
    rules: list[str] | str | None = None


class ModelInterpretation(BaseModel):
    """One model's independent interpretation of the requirement workbook."""
    slot: str
    model_id: str
    status: Literal["completed", "failed"]
    summary: str | None = None
    fields: list[InterpretedField] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    coverage: float | None = Field(default=None, description="Share of canonical keys the model's interpretation covers")
    raw_response: str | None = None
    error: str | None = None
    latency_ms: int | None = None
    usage: dict[str, int] | None = None
    created_at: str
