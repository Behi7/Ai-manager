from __future__ import annotations

import json
import logging
import re
from typing import Any

from anthropic import AsyncAnthropic

from .config import FIELDS, FIELD_BY_KEY, settings
from .prompts import (
    CLASSIFICATION_SYSTEM,
    SUMMARY_SYSTEM,
    correction_system_prompt,
    extractor_system_prompt,
    talker_system_prompt,
)
from .schemas import (
    Classification,
    ExtractionResult,
    TalkerResponse,
    post_validate_extraction,
)

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None


def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = re.sub(r"```$", "", text)
    return text.strip()


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(_strip_json(text))
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Cannot parse JSON from model response")


def _to_anthropic_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    for item in history:
        if item["role"] == "user":
            messages.append({"role": "user", "content": item["content"]})
        elif item["role"] == "talker":
            messages.append({"role": "assistant", "content": item["content"]})

    if not messages:
        messages = [{"role": "user", "content": "Начни диалог."}]

    return messages


async def _request_json(
    system: str,
    history: list[dict[str, str]],
    model: str,
    max_tokens: int = 1024,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}

    if _client is None:
        logger.warning("Anthropic API key is not configured")
        return fallback

    try:
        response = await _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=_to_anthropic_messages(history),
        )

        text = "".join(
            block.text
            for block in response.content
            if hasattr(block, "text")
        )

        return _parse_json(text)
    except Exception:
        logger.exception("LLM request failed")
        return fallback


def _fallback_summary(draft: dict[str, Any]) -> str:
    lines = []

    for field in FIELDS:
        value = draft.get(field["key"])
        if value not in (None, ""):
            lines.append(f"{field['label']}: {value}")

    if not lines:
        return "У меня пока нет данных заявки. Расскажи, пожалуйста, имя, адрес, площадь комнаты, телефон и бюджет. Всё верно? (да/нет)"

    return (
        "Проверьте, пожалуйста, данные:\n"
        + "\n".join(lines)
        + "\nВсё верно? (да/нет)"
    )


async def talker_reply(
    history: list[dict[str, str]],
    extra_instruction: str = "",
) -> TalkerResponse:
    fallback = {
        "reply": "Здравствуйте! Я пока не могу обработать сообщение, потому что не настроен LLM-ключ.",
        "ready_to_check": False,
    }

    data = await _request_json(
        system=talker_system_prompt(extra_instruction),
        history=history,
        model=settings.talker_model,
        fallback=fallback,
    )

    try:
        return TalkerResponse.model_validate(data)
    except Exception:
        logger.exception("Invalid talker response")
        return TalkerResponse.model_validate(fallback)


async def classify_confirmation(history: list[dict[str, str]]) -> Classification:
    if _client is None:
        last_user = next(
            (item["content"] for item in reversed(history) if item["role"] == "user"),
            "",
        )
        normalized = last_user.strip().lower()
        confirmed = normalized in {
            "да",
            "yes",
            "ok",
            "ок",
            "верно",
            "правильно",
            "подтверждаю",
            "всё верно",
            "все верно",
        }
        return Classification(confirmed=confirmed)

    data = await _request_json(
        system=CLASSIFICATION_SYSTEM,
        history=history,
        model=settings.talker_model,
        fallback={"confirmed": False},
    )

    try:
        return Classification.model_validate(data)
    except Exception:
        logger.exception("Invalid classification response")
        return Classification(confirmed=False)


async def summarize_draft(draft: dict[str, Any]) -> str:
    history = [
        {
            "role": "user",
            "content": json.dumps({"draft": draft}, ensure_ascii=False),
        }
    ]

    data = await _request_json(
        system=SUMMARY_SYSTEM,
        history=history,
        model=settings.talker_model,
        fallback={"reply": _fallback_summary(draft), "ready_to_check": False},
    )

    try:
        return TalkerResponse.model_validate(data).reply
    except Exception:
        logger.exception("Invalid summary response")
        return _fallback_summary(draft)


async def extract(history: list[dict[str, str]]) -> ExtractionResult:
    fallback = {field["key"]: None for field in FIELDS}
    fallback.update(
        {
            "status": "incomplete",
            "missing_fields": [field["key"] for field in FIELDS if field.get("required")],
            "invalid_fields": [],
        }
    )

    data = await _request_json(
        system=extractor_system_prompt(),
        history=history,
        model=settings.extractor_model,
        max_tokens=2048,
        fallback=fallback,
    )

    try:
        result = ExtractionResult.model_validate(data)
    except Exception:
        logger.exception("Invalid extractor response")
        result = ExtractionResult.model_validate(fallback)

    return post_validate_extraction(result)


async def correct_field(
    history: list[dict[str, str]],
    draft: dict[str, Any],
) -> dict[str, Any] | None:
    data = await _request_json(
        system=correction_system_prompt(draft),
        history=history,
        model=settings.extractor_model,
        fallback={"field_key": None, "value": None},
    )

    field_key = data.get("field_key")
    value = data.get("value")

    if field_key in FIELD_BY_KEY:
        return {"field_key": field_key, "value": value}

    return None