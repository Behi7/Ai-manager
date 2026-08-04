from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, create_model

from .config import FIELDS, FIELD_BY_KEY


_FIELD_TYPES = {
    "str": (Optional[str], None),
    "float": (Optional[float], None),
    "int": (Optional[int], None),
}

_fields: dict[str, Any] = {}

for field in FIELDS:
    base = _FIELD_TYPES.get(field["type"])
    if base is None:
        raise ValueError(f"Unsupported field type: {field['type']}")
    _fields[field["key"]] = base

_fields["status"] = (Literal["complete", "incomplete"], ...)
_fields["missing_fields"] = (list[str], Field(default_factory=list))
_fields["invalid_fields"] = (list[str], Field(default_factory=list))

ExtractionResult = create_model("ExtractionResult", **_fields)


class TalkerResponse(BaseModel):
    reply: str
    ready_to_check: bool = False


class Classification(BaseModel):
    confirmed: bool


def _is_empty(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def validate_field(key: str, value: Any) -> bool:
    cfg = FIELD_BY_KEY.get(key)
    if not cfg:
        return False

    if _is_empty(value):
        return False

    if cfg["type"] == "float":
        try:
            return float(value) > 0
        except Exception:
            return False

    if cfg["type"] == "int":
        try:
            return int(value) > 0
        except Exception:
            return False

    validation = cfg.get("validation")
    if validation:
        return bool(re.fullmatch(validation, str(value)))

    if key == "address":
        return len(str(value).strip()) >= 5

    return True


def post_validate_extraction(raw: ExtractionResult) -> ExtractionResult:
    data = raw.model_dump()

    missing: list[str] = []
    invalid: list[str] = []

    for field in FIELDS:
        key = field["key"]
        value = data.get(key)

        if _is_empty(value):
            if field.get("required", True):
                missing.append(key)
            continue

        if not validate_field(key, value):
            invalid.append(key)

    data["missing_fields"] = sorted(set(missing + list(data.get("missing_fields", []))))
    data["invalid_fields"] = sorted(set(invalid + list(data.get("invalid_fields", []))))

    if not data["missing_fields"] and not data["invalid_fields"]:
        data["status"] = "complete"
    else:
        data["status"] = "incomplete"

    return ExtractionResult.model_validate(data)