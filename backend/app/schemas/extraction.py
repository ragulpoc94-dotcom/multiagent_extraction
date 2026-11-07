"""Common extraction output contract shared by all nine executions."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FieldResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Any = None
    evidence: str | None = None
    page: int | None = None

    @field_validator("evidence", mode="before")
    @classmethod
    def _evidence_to_str(cls, v: Any) -> Any:
        if v is None or isinstance(v, str):
            return v
        if isinstance(v, list):
            return " ".join(str(x) for x in v)
        return str(v)

    @field_validator("page", mode="before")
    @classmethod
    def _page_to_int(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, (int,)):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str):
            digits = "".join(ch for ch in v if ch.isdigit())
            return int(digits) if digits else None
        if isinstance(v, list) and v:
            return cls._page_to_int(v[0])
        return None


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_generator: str | None = None
    extraction_model: str | None = None
    extracted_fields: dict[str, FieldResult]


FieldStatus = Literal["ok", "missing", "not_returned", "type_error", "unsupported", "page_invalid"]


class FieldValidation(BaseModel):
    key: str
    status: FieldStatus
    value: Any = None
    normalized_value: Any = None
    evidence: str | None = None
    page: int | None = None
    evidence_found: bool | None = None
    issues: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    json_valid: bool
    schema_valid: bool
    parse_error: str | None = None
    fields_expected: int
    fields_returned: int
    fields_filled: int
    missing: int
    not_returned: int
    type_errors: int
    unsupported: int
    unexpected_keys: list[str] = Field(default_factory=list)
    missing_rate: float
    supported_fill_rate: float = Field(
        description="Expected fields with a non-null, type-valid value whose evidence was found in the document"
    )
    fields: dict[str, FieldValidation] = Field(default_factory=dict)


ExecutionStatus = Literal["queued", "running", "completed", "failed", "interrupted", "skipped"]
