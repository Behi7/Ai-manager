import logging

from aiogram import Router, types

from .service import handle_user_message

logger = logging.getLogger(__name__)

router = Router()


@router.message()
async def message_handler(message: types.Message) -> None:
    if not message.text:
        return

    if not message.from_user:
        return

    try:
        await handle_user_message(
            message.bot,
            message.from_user.id,
            message.text,
        )
    except Exception:
        logger.exception("Failed to process message")