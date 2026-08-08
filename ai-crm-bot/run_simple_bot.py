import sys
import asyncio
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

from aiogram import Bot, Dispatcher
from app.config import settings
from app.handlers import router
from app.db import init_db
from app.service import generate_fields_from_amocrm
from app import fields as fields_module
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    
    # Загружаем поля из amoCRM при старте
    logging.info("Starting to load fields from amoCRM...")
    try:
        amo_fields = await generate_fields_from_amocrm()
        if not amo_fields:
            raise RuntimeError("Не удалось загрузить поля из amoCRM - приложение не может работать без полей")
        
        fields_module.update_fields(amo_fields)
        logging.info(f"Successfully loaded {len(amo_fields)} fields from amoCRM on startup")
        for field in amo_fields:
            logging.info(f"  - {field['key']}: {field['label']} (target: {field['amo_target']}, field_id: {field.get('amo_field_id')})")
    except Exception as e:
        logging.error(f"Failed to load fields from amoCRM on startup: {e}")
        raise RuntimeError(f"Критическая ошибка: не удалось загрузить поля из amoCRM. Приложение не может работать без полей. Ошибка: {e}")
    
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    
    logging.info("Starting polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Polling error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
