"""Target schema for one trial's eligibility criteria.

Plain dataclasses with explicit validation so the project has no dependency
beyond the Anthropic SDK. The same definitions are used for the LLM tool
schema, the regex baseline, and the hand-labeled gold set.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

OPERATORS = (">", ">=", "<", "<=", "=")
SEXES = ("ALL", "FEMALE", "MALE")
SECTIONS = ("inclusion", "exclusion")


class SchemaError(ValueError):
    pass


@dataclass
class LabThreshold:
    test: str
    operator: str
    value: float
    section: str
    unit: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LabThreshold":
        try:
            test = str(d["test"]).strip()
            op = str(d["operator"]).strip()
            value = float(d["value"])
            section = str(d["section"]).strip().lower()
        except (KeyError, TypeError, ValueError) as e:
            raise SchemaError(f"bad lab threshold {d!r}: {e}") from e
        if op not in OPERATORS:
            raise SchemaError(f"bad operator {op!r}")
        if section not in SECTIONS:
            raise SchemaError(f"bad section {section!r}")
        unit = d.get("unit")
        unit = str(unit).strip() if unit not in (None, "") else None
        return cls(test=test, operator=op, value=value, section=section, unit=unit)


@dataclass
class Eligibility:
    min_age_years: Optional[float] = None
    max_age_years: Optional[float] = None
    sex: Optional[str] = None
    excludes_pregnancy: Optional[bool] = None
    required_conditions: list[str] = field(default_factory=list)
    excluded_conditions: list[str] = field(default_factory=list)
    lab_thresholds: list[LabThreshold] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Eligibility":
        def num(key: str) -> Optional[float]:
            v = d.get(key)
            if v in (None, ""):
                return None
            try:
                return float(v)
            except (TypeError, ValueError) as e:
                raise SchemaError(f"{key} not a number: {v!r}") from e

        sex = d.get("sex")
        if sex is not None:
            sex = str(sex).upper().strip()
            if sex not in SEXES:
                raise SchemaError(f"bad sex {sex!r}")
        preg = d.get("excludes_pregnancy")
        if preg is not None and not isinstance(preg, bool):
            raise SchemaError(f"excludes_pregnancy must be bool or null, got {preg!r}")

        def strlist(key: str) -> list[str]:
            v = d.get(key) or []
            if not isinstance(v, list):
                raise SchemaError(f"{key} must be a list")
            return [str(x).strip() for x in v if str(x).strip()]

        labs_raw = d.get("lab_thresholds") or []
        if not isinstance(labs_raw, list):
            raise SchemaError("lab_thresholds must be a list")
        return cls(
            min_age_years=num("min_age_years"),
            max_age_years=num("max_age_years"),
            sex=sex,
            excludes_pregnancy=preg,
            required_conditions=strlist("required_conditions"),
            excluded_conditions=strlist("excluded_conditions"),
            lab_thresholds=[LabThreshold.from_dict(x) for x in labs_raw],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# JSON schema handed to the model as a forced tool, so output is always structured.
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "min_age_years": {"type": ["number", "null"], "description": "Minimum age in years, or null if not stated."},
        "max_age_years": {"type": ["number", "null"], "description": "Maximum age in years, or null if not stated."},
        "sex": {"type": "string", "enum": list(SEXES), "description": "ALL unless the text restricts enrollment to one sex."},
        "excludes_pregnancy": {"type": "boolean", "description": "True if pregnant people are excluded."},
        "required_conditions": {
            "type": "array", "items": {"type": "string"},
            "description": "Diseases or conditions a participant must have. Short names. No drugs, procedures or lab values.",
        },
        "excluded_conditions": {
            "type": "array", "items": {"type": "string"},
            "description": "Diseases or conditions that exclude a participant. Short names. No drugs, procedures or lab values.",
        },
        "lab_thresholds": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test": {"type": "string", "description": "Lab or body measure name, e.g. HbA1c, BMI, eGFR."},
                    "operator": {"type": "string", "enum": list(OPERATORS)},
                    "value": {"type": "number"},
                    "unit": {"type": ["string", "null"]},
                    "section": {"type": "string", "enum": list(SECTIONS)},
                },
                "required": ["test", "operator", "value", "section"],
            },
            "description": "Numeric thresholds as written. A range becomes two entries (>= low, <= high).",
        },
    },
    "required": ["min_age_years", "max_age_years", "sex", "excludes_pregnancy",
                 "required_conditions", "excluded_conditions", "lab_thresholds"],
}
