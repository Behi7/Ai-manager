from __future__ import annotations

import logging
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, create_model

from . import fields

logger = logging.getLogger(__name__)


_FIELD_TYPES = {
    "str": (Optional[str], None),
    "float": (Optional[float], None),
    "int": (Optional[int], None),
}

_fields: dict[str, Any] = {}

for field in fields.FIELDS:
    base = _FIELD_TYPES.get(field["type"])
    if base is None:
        raise ValueError(f"Unsupported field type: {field['type']}")
    _fields[field["key"]] = base

_fields["status"] = (Literal["complete", "incomplete"], ...)
_fields["missing_fields"] = (list[str], Field(default_factory=list))
_fields["invalid_fields"] = (list[str], Field(default_factory=list))

ExtractionResult = create_model("ExtractionResult", **_fields)

# Создаем словарь для быстрого доступа к полям по ключу
FIELD_BY_KEY = {field["key"]: field for field in fields.FIELDS}


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


def post_validate_extraction(raw: ExtractionResult, original_llm_data: dict[str, Any] | None = None) -> ExtractionResult:
    logger.info(f"=== POST_VALIDATE START ===")
    logger.info(f"NEW VERSION - with original_llm_data parameter")
    logger.info(f"Input raw: {raw.model_dump()}")
    logger.info(f"Original LLM data: {original_llm_data}")

    data = raw.model_dump()

    # Если есть исходные данные от LLM, используем их для восстановления полей
    if original_llm_data:
        logger.info(f"Restoring fields from LLM data")
        for field in fields.FIELDS:
            key = field["key"]
            if key in original_llm_data and original_llm_data[key] is not None:
                data[key] = original_llm_data[key]
                logger.info(f"Restored {key} = {original_llm_data[key]}")

    logger.info(f"Data after LLM restore: {data}")

    missing: list[str] = []
    invalid: list[str] = []

    for field in fields.FIELDS:
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

    logger.info(f"Data before validation: {data}")

    result = ExtractionResult.model_validate(data)
    logger.info(f"post_validate result: {result.model_dump()}")
    logger.info(f"=== POST_VALIDATE END ===")
    return result