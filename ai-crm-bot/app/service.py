from __future__ import annotations

import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from . import agents
from .amo import AmoCRMClient, AmoCRMError
from . import fields
from .config import settings
from .db import AsyncSessionLocal
from .models import (
    Conversation,
    CrmQueueItem,
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


async def generate_fields_from_amocrm() -> list[dict[str, Any]]:
    """
    Генерирует структуру fields.FIELDS из данных AmoCRM.
    Получает ВСЕ поля (контактов и сделок), но добавляет ТОЛЬКО:
    - 2 системных поля контактов (name, phone)
    - Поля сделок с * в названии
    - Поля контактов с * в названии
    """
    try:
        logger.info("Fetching all custom fields from amoCRM (contacts and leads)")
        custom_fields = await amo_client.get_account_custom_fields()
        logger.info(f"Received custom fields: {list(custom_fields.keys())}")
        
        generated_fields = []
        
        # Системные поля контактов (всегда добавляем как обязательные)
        generated_fields.append({
            "key": "name",
            "label": "Имя контакта",
            "type": "str",
            "required": True,
            "amo_target": "contact",
            "amo_field_id": None,
            "validation": None,
        })
        logger.info("Added system field: name")
        
        generated_fields.append({
            "key": "phone",
            "label": "Телефон",
            "type": "str",
            "required": True,
            "amo_target": "contact",
            "amo_field_id": None,
            "validation": r"^\+998\d{9}$",
        })
        logger.info("Added system field: phone")
        
        # Функция для проверки обязательности поля (по наличию * в названии)
        def is_required_field(field_name: str | None) -> bool:
            if not field_name:
                return False
            return field_name.startswith("*") or "*" in field_name
        
        # Функция для очистки названия от *
        def clean_field_name(field_name: str) -> str:
            return field_name.replace("*", "").strip()
        
        # Получаем ВСЕ поля сделок, но добавляем только с *
        lead_fields = custom_fields.get("leads", [])
        logger.info(f"Found {len(lead_fields)} lead fields")
        
        for field in lead_fields:
            field_id = field.get("id")
            field_name = field.get("name")
            field_type = field.get("type")
            
            if not field_name:
                continue
            
            # Пропускаем системные UTM поля
            code = field.get("code") or ""
            if code.startswith("UTM_"):
                continue
            
            # Добавляем ТОЛЬКО поля с *
            if not is_required_field(field_name):
                logger.info(f"Skipping lead field without *: {field_name}")
                continue
            
            clean_name = clean_field_name(field_name)
            
            # Пропускаем дубликаты системных полей (более точная проверка)
            clean_lower = clean_name.lower()
            if any(keyword in clean_lower for keyword in ["имя", "телефон", "номер"]):
                logger.info(f"Skipping duplicate field: {clean_name}")
                continue
            
            # Определяем тип поля
            python_type = "str"
            if field_type in ["numeric", "financial"]:
                python_type = "float"
            elif field_type == "checkbox":
                python_type = "bool"
            elif field_type == "multitext":
                python_type = "str"
            elif field_type == "file":
                python_type = "str"
            
            generated_fields.append({
                "key": f"lead_{field_id}",
                "label": clean_name,
                "type": python_type,
                "required": True,  # Все добавленные поля обязательные
                "amo_target": "lead",
                "amo_field_id": field_id,
                "validation": None,
            })
            logger.info(f"Added lead field with *: {clean_name} (id: {field_id})")
        
        # Получаем ВСЕ поля контактов, но добавляем только с *
        contact_fields = custom_fields.get("contacts", [])
        logger.info(f"Found {len(contact_fields)} contact fields")
        
        for field in contact_fields:
            field_id = field.get("id")
            field_name = field.get("name")
            field_type = field.get("type")
            
            # Пропускаем поля без имени или PHONE (системное)
            code = field.get("code") or ""
            if not field_name or code == "PHONE":
                continue
            
            # Добавляем ТОЛЬКО поля с *
            if not is_required_field(field_name):
                logger.info(f"Skipping contact field without *: {field_name}")
                continue
            
            clean_name = clean_field_name(field_name)
            
            # Определяем тип поля
            python_type = "str"
            if field_type in ["numeric", "financial"]:
                python_type = "float"
            elif field_type == "checkbox":
                python_type = "bool"
            elif field_type == "multitext":
                python_type = "str"
            elif field_type == "file":
                python_type = "str"
            
            generated_fields.append({
                "key": f"contact_{field_id}",
                "label": clean_name,
                "type": python_type,
                "required": True,  # Все добавленные поля обязательные
                "amo_target": "contact",
                "amo_field_id": field_id,
                "validation": None,
            })
            logger.info(f"Added contact field with *: {clean_name} (id: {field_id})")
        
        logger.info(f"Generated {len(generated_fields)} fields with * from amoCRM")
        
        if not generated_fields:
            raise RuntimeError("Не найдено ни одного поля с * в amoCRM. Приложение не может работать без обязательных полей.")
        
        return generated_fields
        
    except AmoCRMError as e:
        logger.error(f"Failed to generate fields from amoCRM: {e}")
        raise RuntimeError(f"Ошибка подключения к amoCRM: {e}")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def deterministic_summary(draft: dict[str, Any]) -> str:
    logger.info(f"Generating summary for draft: {draft}")
    logger.info(f"Current fields.FIELDS length: {len(fields.fields.FIELDS)}, fields.FIELDS: {fields.fields.FIELDS}")
    
    if not fields.FIELDS:
        logger.error("fields.FIELDS is empty! This is a critical error.")
        return "Критическая ошибка: поля не загружены. Пожалуйста, свяжитесь с поддержкой."
    
    lines = []

    # Показываем только обязательные поля
    for field in fields.FIELDS:
        if field.get("required", False):
            value = draft.get(field["key"])
            if value not in (None, ""):
                lines.append(f"{field['label']}: {value}")

    if not lines:
        # Если нет обязательных полей, просим заполнить все обязательные
        required_labels = [field["label"] for field in fields.FIELDS if field.get("required", False)]
        logger.info(f"No required fields found in draft. Required labels: {required_labels}")
        if required_labels:
            fields_text = ", ".join(required_labels)
            return f"У меня пока нет данных заявки. Расскажи, пожалуйста: {fields_text}. Всё верно? (да/нет)"
        else:
            return "У меня пока нет данных заявки. Расскажите о себе. Всё верно? (да/нет)"

    summary = (
        "Проверьте, пожалуйста, данные:\n"
        + "\n".join(lines)
        + "\nВсё верно? (да/нет)"
    )
    logger.info(f"Generated summary: {summary}")
    return summary


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


async def update_crm_with_draft(
    session,
    conversation: Conversation,
    draft: dict[str, Any],
) -> None:
    """
    Обновляет контакт и лид в amoCRM с новыми данными из draft.
    Вызывается после успешного извлечения данных.
    """
    logger.info(f"Updating CRM with draft for conversation {conversation.id}")

    contact = await session.get(TelegramContact, conversation.telegram_user_id)

    if not contact or not contact.amo_contact_id:
        logger.warning(f"No amoCRM contact for user {conversation.telegram_user_id}, skipping update")
        return

    try:
        # Обновляем контакт
        await amo_client.update_contact(contact.amo_contact_id, draft)
        logger.info(f"Updated amoCRM contact {contact.amo_contact_id} with new data")
    except Exception as e:
        logger.exception(f"Failed to update amoCRM contact {contact.amo_contact_id}: {e}")

    # Ищем последний успешный лид для этой беседы
    stmt = (
        select(CrmSubmission)
        .where(
            CrmSubmission.conversation_id == conversation.id,
            CrmSubmission.status == "success",
            CrmSubmission.amo_lead_id.isnot(None)
        )
        .order_by(CrmSubmission.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    last_submission = result.scalar_one_or_none()

    if last_submission and last_submission.amo_lead_id:
        try:
            # Обновляем лид
            await amo_client.update_lead(last_submission.amo_lead_id, draft, contact.amo_contact_id)
            logger.info(f"Updated amoCRM lead {last_submission.amo_lead_id} with new data")
        except Exception as e:
            logger.exception(f"Failed to update amoCRM lead {last_submission.amo_lead_id}: {e}")
    else:
        logger.info(f"No existing lead for conversation {conversation.id}, skipping lead update")


async def log_message_to_amocrm(
    session,
    conversation: Conversation,
    role: str,
    content: str,
) -> None:
    """
    Отправляет сообщение как заметку в amoCRM.
    Сначала создает контакт и сделку если их нет, затем логирует сообщение.
    """
    contact = await session.get(TelegramContact, conversation.telegram_user_id)
    
    # Если нет контакта в amoCRM, создаем его
    if not contact or not contact.amo_contact_id:
        logger.info(f"No amoCRM contact for user {conversation.telegram_user_id}, creating...")
        try:
            # Создаем контакт в amoCRM с базовыми данными
            draft = conversation.draft_json or {}
            if not draft.get("name"):
                draft["name"] = f"Telegram User {conversation.telegram_user_id}"
            
            contact_id = await amo_client.create_contact(draft)
            
            if not contact:
                contact = TelegramContact(
                    telegram_user_id=conversation.telegram_user_id,
                    first_seen_at=utcnow(),
                    amo_contact_id=contact_id,
                )
                session.add(contact)
            else:
                contact.amo_contact_id = contact_id
            
            await session.flush()
            logger.info(f"Created amoCRM contact {contact_id} for user {conversation.telegram_user_id}")
        except Exception as e:
            logger.exception(f"Failed to create amoCRM contact for user {conversation.telegram_user_id}: {e}")
            return
    
    # Ищем последнюю успешную отправку в amoCRM
    stmt = (
        select(CrmSubmission)
        .where(
            CrmSubmission.conversation_id == conversation.id,
            CrmSubmission.status == "success",
            CrmSubmission.amo_lead_id.isnot(None)
        )
        .order_by(CrmSubmission.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    last_submission = result.scalar_one_or_none()
    
    lead_id = None
    if last_submission:
        lead_id = last_submission.amo_lead_id
        logger.debug(f"Using existing lead {lead_id} for conversation {conversation.id}")
    else:
        # Если нет сделки, создаем её
        logger.info(f"No lead for conversation {conversation.id}, creating...")
        try:
            draft = conversation.draft_json or {}
            if not draft.get("name"):
                draft["name"] = f"Telegram User {conversation.telegram_user_id}"
            
            if not contact or not contact.amo_contact_id:
                logger.error(f"No valid contact for creating lead in conversation {conversation.id}")
                return
            
            contact_id = contact.amo_contact_id
            lead_id = await amo_client.create_lead(draft, contact_id)
            
            # Сохраняем информацию о созданной сделке
            submission = CrmSubmission(
                conversation_id=conversation.id,
                status="success",
                amo_contact_id=contact_id,
                amo_lead_id=lead_id,
                payload=draft,
            )
            session.add(submission)
            await session.flush()
            
            logger.info(f"Created lead {lead_id} for conversation {conversation.id}")
        except Exception as e:
            logger.exception(f"Failed to create lead for conversation {conversation.id}: {e}")
            return
    
    # Формируем текст заметки
    formatted_text = f"[Telegram Bot] {role.upper()}: {content}"
    
    logger.info(f"Attempting to create note for lead {lead_id}, conversation {conversation.id}")
    
    try:
        # Создаем заметку к сделке
        await amo_client.create_note(lead_id, "common", formatted_text, "lead")
        logger.info(f"Logged message to amoCRM for conversation {conversation.id}, lead {lead_id}")
    except Exception as e:
        logger.exception(f"Failed to log message to amoCRM for conversation {conversation.id}: {e}")


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
    logger.info(f"Sending message to user {conversation.telegram_user_id}: {text[:100]}")
    try:
        await bot.send_message(conversation.telegram_user_id, text)
        logger.info(f"Message sent successfully to user {conversation.telegram_user_id}")
    except Exception as e:
        logger.exception(f"Failed to send message to user {conversation.telegram_user_id}: {e}")
        raise
    
    await append_message(
        session,
        conversation,
        "talker",
        text,
        raw_response,
    )
    # Отправить сообщение в amoCRM
    await log_message_to_amocrm(session, conversation, "talker", text)


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

        if contact.last_order_at:
            last_order_at = _ensure_aware(contact.last_order_at)
            if (utcnow() - last_order_at).days <= settings.repeat_days:
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
    try:
        await session.flush()
    except IntegrityError:
        # Concurrent insertion of TelegramContact happened in another process/thread.
        # Rollback the pending transaction and re-load existing contact, then create
        # the conversation associated with that contact.
        await session.rollback()

        contact = await session.get(TelegramContact, user_id)
        if contact:
            if contact.first_seen_at is None:
                contact.first_seen_at = utcnow()

        # Ensure a fresh Conversation instance is created and persisted
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


def _should_retry_crm_error(error: Exception) -> bool:
    if isinstance(error, httpx.RequestError):
        return True

    if isinstance(error, AmoCRMError):
        message = str(error)
        if "amoCRM error" in message:
            try:
                code = int(message.split("amoCRM error")[1].split(":")[0].strip())
            except Exception:
                return False
            return code in {429, 500, 502, 503, 504}
        return False

    return False


async def enqueue_crm_submission(
    session,
    conversation: Conversation,
    draft: dict[str, Any],
    existing_contact_id: int | None,
) -> None:
    queue_item = CrmQueueItem(
        conversation_id=conversation.id,
        payload=draft,
        existing_contact_id=existing_contact_id,
        status="pending",
        next_attempt_at=utcnow(),
    )
    session.add(queue_item)
    session.add(
        CrmSubmission(
            conversation_id=conversation.id,
            status="pending",
            payload=draft,
        )
    )
    conversation.state = State.SUBMITTED
    await session.flush()


async def process_crm_queue_item(bot: Bot, session, item: CrmQueueItem) -> None:
    conversation = await session.get(Conversation, item.conversation_id)
    if conversation is None:
        item.status = "failed"
        item.last_error = "Conversation not found"
        return

    try:
        # Находим существующий лид для этой беседы
        stmt = (
            select(CrmSubmission)
            .where(
                CrmSubmission.conversation_id == item.conversation_id,
                CrmSubmission.status == "success",
                CrmSubmission.amo_lead_id.isnot(None)
            )
            .order_by(CrmSubmission.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        last_submission = result.scalar_one_or_none()
        existing_lead_id = last_submission.amo_lead_id if last_submission else None

        contact_id, lead_id = await amo_client.submit_final(
            draft=item.payload,
            existing_contact_id=item.existing_contact_id,
            existing_lead_id=existing_lead_id,
        )

        item.status = "success"
        item.attempt_count += 1
        item.last_error = None

        session.add(
            CrmSubmission(
                conversation_id=item.conversation_id,
                amo_contact_id=contact_id,
                amo_lead_id=lead_id,
                status="success",
                payload=item.payload,
            )
        )

        contact = await session.get(TelegramContact, conversation.telegram_user_id)
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

        try:
            await send_and_log(
                bot,
                session,
                conversation,
                "Соединение восстановлено, заявка отправлена в amoCRM.",
            )
        except Exception:
            logger.exception("Failed to notify user about CRM queue success")

    except Exception as exc:
        retryable = _should_retry_crm_error(exc)
        item.attempt_count += 1
        item.last_error = str(exc)

        if not retryable or item.attempt_count >= settings.total_retry_limit:
            item.status = "failed"
            await session.flush()

            session.add(
                CrmSubmission(
                    conversation_id=item.conversation_id,
                    status="failed",
                    payload=item.payload,
                )
            )

            await handoff(
                bot,
                session,
                conversation,
                "Ошибка отправки в amoCRM из очереди",
                try_submit_to_crm=False,
            )
            return

        item.next_attempt_at = utcnow() + timedelta(
            minutes=settings.crm_retry_interval_minutes,
        )


async def process_crm_queue(bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(CrmQueueItem)
            .where(
                CrmQueueItem.status == "pending",
                CrmQueueItem.next_attempt_at <= utcnow(),
            )
            .order_by(CrmQueueItem.next_attempt_at.asc())
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        for item in items:
            try:
                await process_crm_queue_item(bot, session, item)
            except Exception:
                logger.exception("Failed to process CRM queue item")

        await session.commit()


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

            # Находим существующий лид для этой беседы
            stmt = (
                select(CrmSubmission)
                .where(
                    CrmSubmission.conversation_id == conversation.id,
                    CrmSubmission.status == "success",
                    CrmSubmission.amo_lead_id.isnot(None)
                )
                .order_by(CrmSubmission.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            last_submission = result.scalar_one_or_none()
            existing_lead_id = last_submission.amo_lead_id if last_submission else None

            contact_id, lead_id = await amo_client.submit_handoff(
                draft=draft,
                existing_contact_id=existing_contact_id,
                existing_lead_id=existing_lead_id,
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
        f"{fields.FIELD_BY_KEY[key]['label']}: {value}"
        for key, value in draft.items()
        if key in fields.FIELD_BY_KEY and value not in (None, "")
    )

    missing = ", ".join(
        field["label"]
        for field in fields.FIELDS
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

    # Находим существующий лид для этой беседы
    stmt = (
        select(CrmSubmission)
        .where(
            CrmSubmission.conversation_id == conversation.id,
            CrmSubmission.status == "success",
            CrmSubmission.amo_lead_id.isnot(None)
        )
        .order_by(CrmSubmission.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    last_submission = result.scalar_one_or_none()
    existing_lead_id = last_submission.amo_lead_id if last_submission else None

    try:
        contact_id, lead_id = await amo_client.submit_final(
            draft=draft,
            existing_contact_id=existing_contact_id,
            existing_lead_id=existing_lead_id,
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

    except (AmoCRMError, httpx.RequestError) as exc:
        logger.exception("amoCRM submission failed")

        if _should_retry_crm_error(exc):
            await enqueue_crm_submission(
                session,
                conversation,
                draft,
                existing_contact_id,
            )

            await send_and_log(
                bot,
                session,
                conversation,
                "Сейчас была проблема с подключением к amoCRM. Заявка поставлена в очередь и будет отправлена автоматически, когда сервис восстановится.",
            )
        else:
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
    logger.info(f"Running extraction with history length: {len(history)}")
    logger.info(f"Current fields.FIELDS: {[f['key'] for f in fields.FIELDS]}")
    
    try:
        extraction = await agents.extract(history)
        logger.info(f"Extraction result: status={extraction.status}, missing={extraction.missing_fields}, invalid={extraction.invalid_fields}")
        logger.info(f"Extracted data: {extraction.model_dump()}")
    except Exception as e:
        logger.exception(f"Failed to run extraction: {e}")
        # Fallback to collecting state with error message
        await send_and_log(
            bot,
            session,
            conversation,
            "Извините, у меня возникли технические проблемы при обработке ваших данных. Пожалуйста, попробуйте позже или свяжитесь с менеджером."
        )
        conversation.state = State.COLLECTING
        return

    session.add(
        ExtractionSnapshot(
            conversation_id=conversation.id,
            extracted_json=extraction.model_dump(),
            status=extraction.status,
            missing_fields=extraction.missing_fields,
        )
    )

    # Собираем все извлеченные данные (даже при incomplete статусе)
    draft = {
        field["key"]: getattr(extraction, field["key"])
        for field in fields.FIELDS
        if getattr(extraction, field["key"], None) not in (None, "")
    }

    logger.info(f"=== CRM UPDATE CHECK ===")
    logger.info(f"Draft from extraction: {draft}")
    logger.info(f"Extraction object fields: {extraction.model_dump()}")
    logger.info(f"Fields.FIELDS: {fields.FIELDS}")

    # Обновляем draft даже при incomplete статусе
    if draft:
        logger.info(f"Updating conversation.draft_json with: {draft}")
        conversation.draft_json = draft
        # Обновляем контакт и лид в amoCRM с текущими данными
        logger.info(f"Calling update_crm_with_draft...")
        await update_crm_with_draft(session, conversation, draft)
        logger.info(f"Updated CRM with partial data: {draft}")
    else:
        logger.warning("No data extracted from extraction, draft is empty")

    if extraction.status == "complete":
        conversation.retry_count = 0
        conversation.field_retry_count = {}
        await send_summary(bot, session, conversation)
        return

    conversation.retry_count = (conversation.retry_count or 0) + 1

    retries = dict(conversation.field_retry_count or {})
    problem_fields = sorted(set(extraction.missing_fields + extraction.invalid_fields))

    for key in problem_fields:
        if key in fields.FIELD_BY_KEY:
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


async def handle_correction(
    bot: Bot,
    session,
    conversation: Conversation,
) -> None:
    logger.info(f"handle_correction: current draft = {conversation.draft_json}")
    history = await get_history(session, conversation.id)
    draft = conversation.draft_json or {}

    try:
        correction = await agents.correct_field(history, draft)
        logger.info(f"Correction result: {correction}")
    except Exception as e:
        logger.exception(f"Failed to get correction: {e}")
        # Fallback to asking user what to correct
        talker = await agents.talker_reply(
            history,
            "\nКлиент хочет исправить данные, но я не понял что именно. "
            "Мягко уточни, какое поле нужно изменить.",
        )
        await send_and_log(
            bot,
            session,
            conversation,
            talker.reply,
            talker.model_dump(),
        )
        return

    if correction:
        key = correction["field_key"]
        value = correction["value"]

        if validate_field(key, value):
            new_draft = dict(draft)
            new_draft[key] = value
            conversation.draft_json = new_draft
            logger.info(f"Updated draft: {new_draft}")

            await send_summary(bot, session, conversation)
            return

        field_label = fields.FIELD_BY_KEY[key]["label"]
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
    
    # Если correction пустой, запускаем экстрактор
    logger.info("No correction detected, running extraction")
    await run_extraction(bot, session, conversation)

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
    logger.info(f"handle_user_message: user_id={user_id}, text={text}")
    
    try:
        async with AsyncSessionLocal() as session:
            logger.info("Getting or creating conversation")
            conversation, created = await get_or_create_conversation(session, user_id)
            logger.info(f"Conversation: state={conversation.state}, created={created}")

            if created and conversation.state == State.CONFIRMING:
                logger.info("Sending summary for new conversation in CONFIRMING state")
                await send_summary(bot, session, conversation)
                await session.commit()
                return

            if conversation.human_takeover or conversation.state == State.HANDED_OFF:
                logger.info(f"Skipping: human_takeover={conversation.human_takeover}, state={conversation.state}")
                return

            logger.info("Appending user message")
            await append_message(session, conversation, "user", text)
            logger.info("Logging message to amoCRM")
            await log_message_to_amocrm(session, conversation, "user", text)

            if conversation.state == State.CONFIRMING:
                logger.info("Processing CONFIRMING state")
                history = await get_history(session, conversation.id)
                
                try:
                    classification = await agents.classify_confirmation(history)
                except Exception as e:
                    logger.exception(f"Failed to classify confirmation: {e}")
                    # Fallback to simple text matching
                    last_user = next(
                        (item["content"] for item in reversed(history) if item["role"] == "user"),
                        "",
                    )
                    normalized = last_user.strip().lower()
                    confirmed = normalized in {"да", "ок", "верно", "правильно", "подтверждаю", "всё верно", "все верно"}
                    classification = type('obj', (object,), {'confirmed': confirmed})()

                if classification.confirmed:
                    logger.info("User confirmed data, submitting to CRM")
                    await submit_to_crm(bot, session, conversation)
                else:
                    logger.info("User rejected data, switching to CORRECTING state")
                    conversation.state = State.CORRECTING

                    try:
                        talker = await agents.talker_reply(
                            history,
                            "\nКлиент сказал, что данные неверны. "
                            "Спроси, что именно нужно исправить, коротко и по-человечески.",
                        )
                    except Exception as e:
                        logger.exception(f"Failed to get talker reply: {e}")
                        talker = type('obj', (object,), {'reply': "Что именно нужно исправить?", 'model_dump': lambda: {}})()

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
                logger.info("Processing CORRECTING state")
                await handle_correction(bot, session, conversation)
                await session.commit()
                return

            if conversation.state == State.CLARIFYING:
                logger.info("Switching from CLARIFYING to COLLECTING state")
                conversation.state = State.COLLECTING

            logger.info("Getting conversation history")
            history = await get_history(session, conversation.id)

            try:
                logger.info("Getting talker reply")
                talker = await agents.talker_reply(history)
                logger.info(f"Talker reply received: {talker.reply[:100] if talker.reply else 'empty'}")
            except Exception as e:
                logger.exception(f"Failed to get talker reply: {e}")
                # Use deterministic fallback if LLM fails completely
                draft = conversation.draft_json or {}
                text = deterministic_summary(draft)
                logger.info(f"Using deterministic fallback: {text[:100]}")
                await send_and_log(bot, session, conversation, text)
                return

            logger.info("Sending talker reply to user")
            await send_and_log(
                bot,
                session,
                conversation,
                talker.reply,
                talker.model_dump(),
            )

            if talker.ready_to_check:
                logger.info("Talker is ready to check, running extraction")
                await run_extraction(bot, session, conversation)

            logger.info("Committing session")
            await session.commit()
            logger.info("handle_user_message completed successfully")
    except Exception as e:
        logger.exception(f"Error in handle_user_message: {e}")


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
                # Проверяем, существует ли еще этот чат в Telegram
                try:
                    await bot.get_chat(conversation.telegram_user_id)
                except Exception as chat_error:
                    logger.warning(f"Chat {conversation.telegram_user_id} not found, skipping timeout reminder")
                    # Помечаем диалог как завершенный если чат не существует
                    conversation.state = State.SUBMITTED
                    continue
                
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