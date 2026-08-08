from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover
    AsyncAnthropic = None

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None

from . import fields
from .fields import FIELD_BY_KEY
from .config import settings
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

_anthropic_client = (
    AsyncAnthropic(api_key=settings.anthropic_api_key)
    if AsyncAnthropic and settings.anthropic_api_key
    else None
)


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


def _to_gemini_prompt(system: str, history: list[dict[str, str]]) -> str:
    lines = [system.strip()]

    for item in history:
        role = "Пользователь" if item["role"] == "user" else "Ассистент"
        lines.append(f"{role}: {item['content']}")

    lines.append("Ответ должен быть только JSON без markdown и пояснений:")
    return "\n\n".join(lines)


async def _request_anthropic_json(
    system: str,
    history: list[dict[str, str]],
    model: str,
    max_tokens: int = 1024,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}

    if _anthropic_client is None:
        logger.warning("Anthropic API key is not configured")
        return fallback

    try:
        response = await _anthropic_client.messages.create(
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


async def _request_gemini_json(
    system: str,
    history: list[dict[str, str]],
    model: str,
    max_tokens: int = 1024,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}

    if genai is None:
        logger.warning("Gemini package is not installed")
        return fallback

    if not settings.gemini_api_key:
        logger.warning("Gemini API key is not configured")
        return fallback

    genai.configure(api_key=settings.gemini_api_key)
    llm = genai.GenerativeModel(model_name=model)
    prompt = _to_gemini_prompt(system, history)

    try:
        response = await llm.generate_content_async(
            prompt,
            generation_config={
                "temperature": 0.0,
                "max_output_tokens": max_tokens,
            },
        )

        text = getattr(response, "text", None) or ""

        return _parse_json(text)
    except Exception as e:
        logger.exception("LLM request failed")

        # If the model is no longer available, try a safe fallback (talker model).
        try:
            msg = str(e)
        except Exception:
            msg = ""

        if "no longer available" in msg and model != settings.talker_model:
            try:
                logger.info("Attempting fallback to talker model %s", settings.talker_model)
                genai.configure(api_key=settings.gemini_api_key)
                fallback_llm = genai.GenerativeModel(model_name=settings.talker_model)
                response2 = await fallback_llm.generate_content_async(
                    prompt,
                    generation_config={"temperature": 0.0, "max_output_tokens": max_tokens},
                )
                text2 = getattr(response2, "text", None) or ""
                return _parse_json(text2)
            except Exception:
                logger.exception("Fallback LLM request failed")

        return fallback


async def _request_groq_json(
    system: str,
    history: list[dict[str, str]],
    model: str,
    max_tokens: int = 1024,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}

    if not settings.groq_api_key:
        logger.warning("Groq API key is not configured")
        return fallback

    prompt = _to_gemini_prompt(system, history)
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_tokens,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                settings.groq_api_url,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            text = _extract_groq_text(response.json())
            return _parse_json(text)
    except Exception:
        logger.exception("LLM request failed")
        return fallback


def _extract_groq_text(payload: Any) -> str:
    if isinstance(payload, dict):
        output = payload.get("output")

        if isinstance(output, str):
            return output

        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    content = item.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        parts.extend(str(chunk) for chunk in content)
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    parts.append(str(item))
            return "".join(parts)

        if isinstance(payload.get("text"), str):
            return payload["text"]

        if payload.get("response") is not None:
            return json.dumps(payload["response"], ensure_ascii=False)

    return json.dumps(payload, ensure_ascii=False) if payload is not None else ""


async def _request_json(
    system: str,
    history: list[dict[str, str]],
    model: str,
    max_tokens: int = 1024,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = settings.llm_provider.strip().lower()

    if provider == "gemini":
        return await _request_gemini_json(
            system=system,
            history=history,
            model=model,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    if provider == "anthropic":
        return await _request_anthropic_json(
            system=system,
            history=history,
            model=model,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    if provider == "groq":
        return await _request_groq_json(
            system=system,
            history=history,
            model=model,
            max_tokens=max_tokens,
            fallback=fallback,
        )

    logger.warning("Unknown LLM provider %s, using Anthropic fallback", settings.llm_provider)
    return await _request_anthropic_json(
        system=system,
        history=history,
        model=model,
        max_tokens=max_tokens,
        fallback=fallback,
    )


def _fallback_summary(draft: dict[str, Any]) -> str:
    lines = []

    for field in fields.FIELDS:
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
        "reply": "Извините, у меня технические проблемы с AI-сервисом. Пожалуйста, попробуйте позже или свяжитесь с менеджером.",
        "ready_to_check": False,
    }

    try:
        data = await _request_json(
            system=talker_system_prompt(extra_instruction),
            history=history,
            model=settings.talker_model,
            fallback=fallback,
        )
    except Exception as e:
        logger.exception(f"LLM request failed for talker_reply: {e}")
        return TalkerResponse.model_validate(fallback)

    try:
        return TalkerResponse.model_validate(data)
    except Exception:
        logger.exception("Invalid talker response")
        return TalkerResponse.model_validate(fallback)


async def classify_confirmation(history: list[dict[str, str]]) -> Classification:
    if _anthropic_client is None:
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

    try:
        data = await _request_json(
            system=CLASSIFICATION_SYSTEM,
            history=history,
            model=settings.talker_model,
            fallback={"confirmed": False},
        )
    except Exception as e:
        logger.exception(f"LLM request failed for classify_confirmation: {e}")
        return Classification(confirmed=False)

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

    try:
        data = await _request_json(
            system=SUMMARY_SYSTEM,
            history=history,
            model=settings.talker_model,
            fallback={"reply": _fallback_summary(draft), "ready_to_check": False},
        )
    except Exception as e:
        logger.exception(f"LLM request failed for summarize_draft: {e}")
        return _fallback_summary(draft)

    try:
        return TalkerResponse.model_validate(data).reply
    except Exception:
        logger.exception("Invalid summary response")
        return _fallback_summary(draft)


async def extract(history: list[dict[str, str]]) -> ExtractionResult:
    logger.info(f"=== EXTRACT START ===")
    logger.info(f"History length: {len(history)}")
    logger.info(f"History: {history}")
    logger.info(f"Fields: {[f['key'] for f in fields.FIELDS]}")

    fallback = {field["key"]: None for field in fields.FIELDS}
    fallback.update(
        {
            "status": "incomplete",
            "missing_fields": [field["key"] for field in fields.FIELDS if field.get("required")],
            "invalid_fields": [],
        }
    )
    logger.info(f"Fallback: {fallback}")

    try:
        data = await _request_json(
            system=extractor_system_prompt(),
            history=history,
            model=settings.extractor_model,
            max_tokens=2048,
            fallback=fallback,
        )
        logger.info(f"LLM extractor raw response: {data}")
    except Exception as e:
        logger.exception(f"LLM request failed for extract: {e}")
        data = fallback

    # If the extractor returned an incomplete result (possible model unavailable
    # or returned non-JSON), try once more using the talker model as a fallback.
    try:
        status = data.get("status")
    except Exception:
        status = None

    if status != "complete" and settings.talker_model and settings.talker_model != settings.extractor_model:
        logger.info("Extractor incomplete — retrying with talker model %s", settings.talker_model)
        data2 = await _request_json(
            system=extractor_system_prompt(),
            history=history,
            model=settings.talker_model,
            max_tokens=2048,
            fallback=fallback,
        )

        try:
            if data2.get("status") == "complete":
                data = data2
        except Exception:
            pass

    try:
        result = ExtractionResult.model_validate(data)
        logger.info(f"ExtractionResult after model_validate: {result.model_dump()}")
    except Exception:
        logger.exception("Invalid extractor response")
        result = ExtractionResult.model_validate(fallback)

    validated = post_validate_extraction(result, data)
    logger.info(f"ExtractionResult after post_validate: {validated.model_dump()}")

    return validated


async def correct_field(
    history: list[dict[str, str]],
    draft: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        data = await _request_json(
            system=correction_system_prompt(draft),
            history=history,
            model=settings.extractor_model,
            fallback={"field_key": None, "value": None},
        )
    except Exception as e:
        logger.exception(f"LLM request failed for correct_field: {e}")
        return None

    field_key = data.get("field_key")
    value = data.get("value")

    if field_key in FIELD_BY_KEY:
        return {"field_key": field_key, "value": value}

    return None