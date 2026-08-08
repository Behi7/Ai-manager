import logging
import asyncio
from collections import deque
from threading import Lock
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from sqlalchemy import select, update, delete

from .service import handle_user_message
from .db import AsyncSessionLocal
from .config import settings
from .models import (
    Conversation,
    Message,
    TelegramContact,
    CrmSubmission,
    CrmQueueItem,
    ExtractionSnapshot,
    Handoff,
)

logger = logging.getLogger(__name__)

router = Router()

# Хранилище ID обработанных сообщений
_processed_message_ids = set()
# Ограниченная очередь для очистки старых ID
_message_id_queue = deque(maxlen=1000)
# Блокировка для потокобезопасности
_lock = Lock()

# Debounce механизм для объединения сообщений
_pending_messages = {}  # {user_id: {"messages": [], "timer": None, "last_message_time": datetime}}
_debounce_lock = Lock()


def is_duplicate_message(message_id: int) -> bool:
    """
    Проверяет, обрабатывалось ли сообщение с таким ID ранее.
    """
    with _lock:
        if message_id in _processed_message_ids:
            return True

        # Добавляем ID в хранилище
        _processed_message_ids.add(message_id)
        _message_id_queue.append(message_id)

        # Очищаем хранилище от старых ID, превышающих maxlen очереди
        while len(_processed_message_ids) > len(_message_id_queue):
            old_id = _message_id_queue.popleft()
            _processed_message_ids.discard(old_id)

        return False


async def process_pending_messages(user_id: int, bot):
    """
    Обрабатывает накопленные сообщения пользователя.
    """
    with _debounce_lock:
        if user_id not in _pending_messages:
            return

        pending = _pending_messages[user_id]
        messages = pending["messages"]

        if not messages:
            del _pending_messages[user_id]
            return

        # Объединяем все сообщения в один текст
        combined_text = " ".join(messages)

        # Очищаем pending
        del _pending_messages[user_id]

        logger.info(f"Processing combined messages for user {user_id}: {combined_text[:100]}")

        try:
            await handle_user_message(bot, user_id, combined_text)
        except Exception as e:
            logger.exception(f"Failed to process combined messages for user {user_id}: {e}")


async def add_pending_message(user_id: int, text: str, bot):
    """
    Добавляет сообщение в очередь ожидания и сбрасывает таймер.
    """
    with _debounce_lock:
        current_time = datetime.now(timezone.utc)

        if user_id in _pending_messages:
            # Отменяем старый таймер
            old_timer = _pending_messages[user_id]["timer"]
            if old_timer:
                old_timer.cancel()

            # Добавляем новое сообщение
            _pending_messages[user_id]["messages"].append(text)
            _pending_messages[user_id]["last_message_time"] = current_time
        else:
            # Создаем новую запись
            _pending_messages[user_id] = {
                "messages": [text],
                "timer": None,
                "last_message_time": current_time
            }

        # Создаем новый таймер
        timer = asyncio.create_task(
            asyncio.sleep(settings.message_debounce_seconds)
        )
        timer.add_done_callback(lambda t: asyncio.create_task(process_pending_messages(user_id, bot)))

        _pending_messages[user_id]["timer"] = timer
        logger.info(f"Added pending message for user {user_id}, timer reset for {settings.message_debounce_seconds}s")


@router.message(F.text == "/reset")
async def reset_command(message: types.Message) -> None:
    """Сбрасывает состояние conversation пользователя"""
    if not message.from_user:
        return
    
    logger.info(f"Reset command from user {message.from_user.id}")
    
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                update(Conversation)
                .where(Conversation.telegram_user_id == message.from_user.id)
                .values(
                    state="COLLECTING",
                    human_takeover=False,
                    retry_count=0,
                    field_retry_count={}
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount > 0:
                await message.bot.send_message(
                    message.from_user.id,
                    "✅ Ваш диалог сброшен. Можете начать заново!"
                )
                logger.info(f"Reset conversation for user {message.from_user.id}")
            else:
                await message.bot.send_message(
                    message.from_user.id,
                    "⚠️ Нет активного диалога для сброса. Напишите /start для начала."
                )
    except Exception as e:
        logger.exception(f"Failed to reset conversation for user {message.from_user.id}: {e}")
        await message.bot.send_message(
            message.from_user.id,
            "❌ Ошибка при сбросе диалога. Попробуйте позже."
        )


@router.message(F.text == "/clean")
async def clean_command(message: types.Message) -> None:
    """Полностью удаляет все данные пользователя"""
    if not message.from_user:
        return
    
    logger.info(f"Clean command from user {message.from_user.id}")
    
    try:
        async with AsyncSessionLocal() as session:
            user_id = message.from_user.id
            
            # Находим все conversation пользователя
            conv_stmt = select(Conversation).where(Conversation.telegram_user_id == user_id)
            conv_result = await session.execute(conv_stmt)
            conversations = conv_result.scalars().all()
            
            if not conversations:
                await message.bot.send_message(
                    user_id,
                    "⚠️ Нет данных для удаления."
                )
                return
            
            deleted_count = 0
            
            # Удаляем все связанные данные для каждой conversation
            for conv in conversations:
                # Удаляем сообщения
                await session.execute(
                    delete(Message).where(Message.conversation_id == conv.id)
                )
                
                # Удаляем extraction snapshots
                await session.execute(
                    delete(ExtractionSnapshot).where(ExtractionSnapshot.conversation_id == conv.id)
                )
                
                # Удаляем CRM submissions
                await session.execute(
                    delete(CrmSubmission).where(CrmSubmission.conversation_id == conv.id)
                )
                
                # Удаляем CRM queue items
                await session.execute(
                    delete(CrmQueueItem).where(CrmQueueItem.conversation_id == conv.id)
                )
                
                # Удаляем handoffs
                await session.execute(
                    delete(Handoff).where(Handoff.conversation_id == conv.id)
                )
                
                # Удаляем саму conversation
                await session.execute(
                    delete(Conversation).where(Conversation.id == conv.id)
                )
                
                deleted_count += 1
            
            # Удаляем telegram contact
            await session.execute(
                delete(TelegramContact).where(TelegramContact.telegram_user_id == user_id)
            )
            
            await session.commit()
            
            await message.bot.send_message(
                user_id,
                f"✅ Все ваши данные удалены ({deleted_count} диалогов). Можете начать заново!"
            )
            logger.info(f"Cleaned all data for user {user_id}: {deleted_count} conversations deleted")
            
    except Exception as e:
        logger.exception(f"Failed to clean data for user {message.from_user.id}: {e}")
        await message.bot.send_message(
            message.from_user.id,
            "❌ Ошибка при удалении данных. Попробуйте позже."
        )


@router.message()
async def message_handler(message: types.Message) -> None:
    logger.info(f"Received message: id={message.message_id}, text={message.text}, from_user={message.from_user}")
    
    if not message.text:
        logger.info("Message rejected: no text")
        return

    if not message.from_user:
        logger.info("Message rejected: no from_user")
        return

    # Проверяем на дубликат перед обработкой
    if is_duplicate_message(message.message_id):
        logger.info(f"Ignoring duplicate message {message.message_id} from user {message.from_user.id}")
        return

    # Пропускаем команды
    if message.text.startswith("/"):
        logger.info(f"Command detected, processing immediately: {message.text}")
        try:
            await handle_user_message(
                message.bot,
                message.from_user.id,
                message.text,
            )
            logger.info(f"Successfully processed command from user {message.from_user.id}")
        except Exception as e:
            logger.exception(f"Failed to process command from user {message.from_user.id}: {e}")
        return

    # Используем debounce механизм для обычных сообщений
    logger.info(f"Adding message to debounce queue for user {message.from_user.id}")
    try:
        await add_pending_message(message.from_user.id, message.text, message.bot)
    except Exception as e:
        logger.exception(f"Failed to add pending message for user {message.from_user.id}: {e}")
        # Fallback: process immediately if debounce fails
        try:
            await handle_user_message(
                message.bot,
                message.from_user.id,
                message.text,
            )
        except Exception as fallback_error:
            logger.exception(f"Fallback processing also failed for user {message.from_user.id}: {fallback_error}")