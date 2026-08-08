import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from .config import settings
from .db import init_db
from .handlers import router
from .scheduler import start_scheduler
from .service import generate_fields_from_amocrm
from . import fields as fields_module

logging.basicConfig(level=logging.INFO)

if not settings.telegram_bot_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    
    # Temporarily disable for testing
    # logging.info("Starting scheduler...")
    # try:
    #     start_scheduler(bot)
    #     logging.info("Scheduler started successfully")
    # except Exception as e:
    #     logging.error(f"Failed to start scheduler: {e}")
    #     raise

    # Start polling as background task
    logging.info("Starting polling task...")
    try:
        polling_task = asyncio.create_task(dp.start_polling(bot))
        logging.info("Polling task created successfully")
    except Exception as e:
        logging.error(f"Failed to create polling task: {e}")
        raise

    yield

    logging.info("Shutting down...")
    if 'polling_task' in locals():
        polling_task.cancel()
        logging.info("Polling task cancelled")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status":"ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )
