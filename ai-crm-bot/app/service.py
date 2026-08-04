from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import Bot
from sqlalchemy import select

from . import agents
from .amo import AmoCRMClient, AmoCRMError
from .config import FIELDS, FIELD_BY_KEY, settings
from .db import AsyncSessionLocal
from .models import (
    Conversation,
    CrmSubmission,
    ExtractionSnapshot,
    Handoff,
    Message,
    State,
    TelegramContact,
)
from .schemas import validate_field

logger = logging.getLogger(__name__)

amo_client = AmoCRMClient()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def deterministic_summary(draft: dict[str, Any]) -> str:
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


async def notify_manager(bot: Bot, text: str) -> None:
    if not settings.manager_telegram_chat_id:
        return

    try:
        await bot.send_message(settings.manager_telegram_chat_id, text)
    except Exception:
        logger.exception("Failed to notify manager")


async def get_history(
    session,
    conversation_id,
) -> list[dict[str, str]]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    result = await session.execute(stmt)
    messages = result.scalars().all()

    return [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in messages
        if message.role in {"user", "talker"}
    ]


async def append_message(
    session,
    conversation: Conversation,
    role: str,
    content: str,
    raw_response: dict | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
        raw_response=raw_response,
    )

    session.add(message)
    conversation.updated_at = utcnow()
    await session.flush()

    return message


async def send_and_log(
    bot: Bot,
    session,
    conversation: Conversation,
    text: str,
    raw_response: dict | None = None,
) -> None:
    await bot.send_message(conversation.telegram_user_id, text)
    await append_message(
        session,
        conversation,
        "talker",
        text,
        raw_response,
    )


async def get_latest_conversation(session, user_id: int) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.telegram_user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_conversation(session, user_id: int) -> Conversation:
    state = State.COLLECTING
    draft: dict[str, Any] = {}

    contact = await session.get(TelegramContact, user_id)

    if contact:
        if contact.first_seen_at is None:
            contact.first_seen_at = utcnow()

        if (
            contact.last_order_at
            and (utcnow() - contact.last_order_at).days <= settings.repeat_days
        ):
            if contact.amo_contact_id:
                try:
                    draft = await amo_client.get_contact_draft(contact.amo_contact_id)
                except Exception:
                    logger.exception("Failed to fetch repeat client draft from amoCRM")

            if draft:
                state = State.CONFIRMING
    else:
        contact = TelegramContact(
            telegram_user_id=user_id,
            first_seen_at=utcnow(),
        )
        session.add(contact)

    conversation = Conversation(
        telegram_user_id=user_id,
        state=state,
        draft_json=draft,
        field_retry_count={},
    )

    session.add(conversation)
    await session.flush()

    return conversation


async def get_or_create_conversation(
    session,
    user_id: int,
) -> tuple[Conversation, bool]:
    conversation = await get_latest_conversation(session, user_id)

    if conversation is None or conversation.state == State.SUBMITTED:
        conversation = await create_conversation(session, user_id)
        return conversation, True

    return conversation, False


async def send_summary(
    bot: Bot,
    session,
    conversation: Conversation,
) -> None:
    draft = conversation.draft_json or {}

    try:
        text = await agents.summarize_draft(draft)
    except Exception:
        logger.exception("Failed to summarize draft")
        text = deterministic_summary(draft)

    if not text:
        text = deterministic_summary(draft)

    await send_and_log(bot, session, conversation, text)
    conversation.state = State.CONFIRMING


async def handoff(
    bot: Bot,
    session,
    conversation: Conversation,
    reason: str,
    try_submit_to_crm: bool = True,
) -> None:
    if conversation.human_takeover:
        return

    conversation.state = State.HANDED_OFF
    conversation.human_takeover = True

    session.add(
        Handoff(
            conversation_id=conversation.id,
            reason=reason,
        )
    )

    draft = conversation.draft_json or {}

    if try_submit_to_crm:
        try:
            contact = await session.get(TelegramContact, conversation.telegram_user_id)
            existing_contact_id = contact.amo_contact_id if contact else None

            contact_id, lead_id = await amo_client.submit_handoff(
                draft=draft,
                existing_contact_id=existing_contact_id,
                reason=reason,
            )

            session.add(
                CrmSubmission(
                    conversation_id=conversation.id,
                    amo_contact_id=contact_id,
                    amo_lead_id=lead_id,
                    status="handoff",
                    payload=draft,
                )
            )

            if contact:
                contact.amo_contact_id = contact_id
        except Exception:
            logger.exception("Failed to submit handoff draft to amoCRM")
            session.add(
                CrmSubmission(
                    conversation_id=conversation.id,
                    status="handoff_failed",
                    payload=draft,
                )
            )

    await send_and_log(
        bot,
        session,
        conversation,
        "Я передал ваш вопрос менеджеру. Он свяжется с вами в ближайшее время.",
    )

    collected = "\n".join(
        f"{FIELD_BY_KEY[key]['label']}: {value}"
        for key, value in draft.items()
        if key in FIELD_BY_KEY and value not in (None, "")
    )

    missing = ", ".join(
        field["label"]
        for field in FIELDS
        if draft.get(field["key"]) in (None, "")
    )

    await notify_manager(
        bot,
        "Эскалация по диалогу.\n"
        f"Причина: {reason}\n"
        f"Telegram user id: {conversation.telegram_user_id}\n"
        f"Conversation id: {conversation.id}\n\n"
        f"Собрано:\n{collected or 'ничего'}\n\n"
        f"Не хватает: {missing or 'нет'}",
    )


async def submit_to_crm(
    bot: Bot,
    session,
    conversation: Conversation,
) -> None:
    stmt = (
        select(CrmSubmission)
        .where(
            CrmSubmission.conversation_id == conversation.id,
            CrmSubmission.status == "success",
        )
        .limit(1)
    )
    result = await session.execute(stmt)

    if result.scalar_one_or_none():
        conversation.state = State.SUBMITTED
        await send_and_log(
            bot,
            session,
            conversation,
            "Заявка уже была отправлена.",
        )
        return

    draft = conversation.draft_json or {}
    contact = await session.get(TelegramContact, conversation.telegram_user_id)
    existing_contact_id = contact.amo_contact_id if contact else None

    try:
        contact_id, lead_id = await amo_client.submit_final(
            draft=draft,
            existing_contact_id=existing_contact_id,
        )

        session.add(
            CrmSubmission(
                conversation_id=conversation.id,
                amo_contact_id=contact_id,
                amo_lead_id=lead_id,
                status="success",
                payload=draft,
            )
        )

        if contact is None:
            contact = TelegramContact(
                telegram_user_id=conversation.telegram_user_id,
                amo_contact_id=contact_id,
                first_seen_at=utcnow(),
                last_order_at=utcnow(),
            )
            session.add(contact)
        else:
            contact.amo_contact_id = contact_id
            contact.last_order_at = utcnow()

        conversation.state = State.SUBMITTED

        await send_and_log(
            bot,
            session,
            conversation,
            "Спасибо! Я подтвердил заявку и передал её менеджеру. Мы свяжемся с вами по указанному номеру.",
        )

    except AmoCRMError:
        logger.exception("amoCRM submission failed")

        session.add(
            CrmSubmission(
                conversation_id=conversation.id,
                status="failed",
                payload=draft,
            )
        )

        await handoff(
            bot,
            session,
            conversation,
            "Ошибка отправки в amoCRM",
            try_submit_to_crm=False,
        )

    except Exception:
        logger.exception("Unexpected CRM submission error")

        session.add(
            CrmSubmission(
                conversation_id=conversation.id,
                status="failed",
                payload=draft,
            )
        )

        await handoff(
            bot,
            session,
            conversation,
            "Непредвиденная ошибка при отправке в CRM",
            try_submit_to_crm=False,
        )


async def run_extraction(
    bot: Bot,
    session,
    conversation: Conversation,
) -> None:
    conversation.state = State.EXTRACTING

    history = await get_history(session, conversation.id)
    extraction = await agents.extract(history)

    session.add(
        ExtractionSnapshot(
            conversation_id=conversation.id,
            extracted_json=extraction.model_dump(),
            status=extraction.status,
            missing_fields=extraction.missing_fields,
        )
    )

    if extraction.status == "complete":
        draft = {
            field["key"]: getattr(extraction, field["key"])
            for field in FIELDS
            if getattr(extraction, field["key"], None) not in (None, "")
        }

        conversation.draft_json = draft
        conversation.retry_count = 0
        conversation.field_retry_count = {}

        await send_summary(bot, session, conversation)
        return

    conversation.retry_count = (conversation.retry_count or 0) + 1

    retries = dict(conversation.field_retry_count or {})
    problem_fields = sorted(set(extraction.missing_fields + extraction.invalid_fields))

    for key in problem_fields:
        if key in FIELD_BY_KEY:
            retries[key] = retries.get(key, 0) + 1

    conversation.field_retry_count = retries

    if (
        conversation.retry_count >= settings.total_retry_limit
        or any(value >= settings.field_retry_limit for value in retries.values())
    ):
        await handoff(
            bot,
            session,
            conversation,
            "Превышен лимит попыток извлечения",
        )
        return

    conversation.state = State.CLARIFYING

    missing_labels = [
        FIELD_BY_KEY[key]["label"]
        for key in extraction.missing_fields
        if key in FIELD_BY_KEY
    ]
    invalid_labels = [
        FIELD_BY_KEY[key]["label"]
        for key in extraction.invalid_fields
        if key in FIELD_BY_KEY
    ]

    extra = (
        "\nСейчас нужно мягко уточнить данные клиента. "
        f"Не хватает: {', '.join(missing_labels) or 'ничего'}. "
        f"Некорректно: {', '.join(invalid_labels) or 'ничего'}. "
        "Не перечисляй технические названия полей."
    )

    talker = await agents.talker_reply(history, extra)
    await send_and_log(
        bot,
        session,
        conversation,
        talker.reply,
        talker.model_dump(),
    )


async def handle_correction(
    bot: Bot,
    session,
    conversation: Conversation,
) -> None:
    history = await get_history(session, conversation.id)
    draft = conversation.draft_json or {}

    correction = await agents.correct_field(history, draft)

    if correction:
        key = correction["field_key"]
        value = correction["value"]

        if validate_field(key, value):
            new_draft = dict(draft)
            new_draft[key] = value
            conversation.draft_json = new_draft

            await send_summary(bot, session, conversation)
            return

        field_label = FIELD_BY_KEY[key]["label"]
        extra = (
            f"\nКлиент пытается исправить поле '{field_label}', но значение некорректно. "
            "Мягко переспроси только это поле."
        )

        talker = await agents.talker_reply(history, extra)
        await send_and_log(
            bot,
            session,
            conversation,
            talker.reply,
            talker.model_dump(),
        )
        return

    talker = await agents.talker_reply(
        history,
        "\nКлиент хочет исправить данные, но неясно, что именно. "
        "Мягко уточни, какое поле нужно изменить.",
    )

    await send_and_log(
        bot,
        session,
        conversation,
        talker.reply,
        talker.model_dump(),
    )


async def handle_user_message(
    bot: Bot,
    user_id: int,
    text: str,
) -> None:
    async with AsyncSessionLocal() as session:
        conversation, created = await get_or_create_conversation(session, user_id)

        if created and conversation.state == State.CONFIRMING:
            await send_summary(bot, session, conversation)
            await session.commit()
            return

        if conversation.human_takeover or conversation.state == State.HANDED_OFF:
            return

        await append_message(session, conversation, "user", text)

        if conversation.state == State.CONFIRMING:
            history = await get_history(session, conversation.id)
            classification = await agents.classify_confirmation(history)

            if classification.confirmed:
                await submit_to_crm(bot, session, conversation)
            else:
                conversation.state = State.CORRECTING

                talker = await agents.talker_reply(
                    history,
                    "\nКлиент сказал, что данные неверны. "
                    "Спроси, что именно нужно исправить, коротко и по-человечески.",
                )

                await send_and_log(
                    bot,
                    session,
                    conversation,
                    talker.reply,
                    talker.model_dump(),
                )

            await session.commit()
            return

        if conversation.state == State.CORRECTING:
            await handle_correction(bot, session, conversation)
            await session.commit()
            return

        if conversation.state == State.CLARIFYING:
            conversation.state = State.COLLECTING

        history = await get_history(session, conversation.id)

        talker = await agents.talker_reply(history)

        await send_and_log(
            bot,
            session,
            conversation,
            talker.reply,
            talker.model_dump(),
        )

        if talker.ready_to_check:
            await run_extraction(bot, session, conversation)

        await session.commit()


async def check_timeouts(bot: Bot) -> None:
    threshold = utcnow() - timedelta(hours=settings.timeout_hours)

    async with AsyncSessionLocal() as session:
        stmt = select(Conversation).where(
            Conversation.human_takeover.is_(False),
            Conversation.state.notin_([State.SUBMITTED, State.HANDED_OFF]),
            Conversation.updated_at < threshold,
        )

        result = await session.execute(stmt)
        conversations = result.scalars().all()

        for conversation in conversations:
            try:
                await send_and_log(
                    bot,
                    session,
                    conversation,
                    "Напоминание: мы остановились на оформлении заявки. Продолжим?",
                )
            except Exception:
                logger.exception("Failed to send timeout reminder")
                conversation.updated_at = utcnow()

        await session.commit()