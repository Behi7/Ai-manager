import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from .config import settings
from .db import init_db
from .handlers import router
from .service import generate_fields_from_amocrm
from . import fields as fields_module

logger = logging.getLogger(__name__)

if not settings.telegram_bot_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    logger.info("Loading fields from amoCRM...")
    try:
        amo_fields = await generate_fields_from_amocrm()
        if not amo_fields:
            raise RuntimeError("Failed to load fields from amoCRM")

        fields_module.update_fields(amo_fields)
        logger.info(f"Loaded {len(amo_fields)} fields from amoCRM")
        for field in amo_fields:
            logger.info(f"  - {field['key']}: {field['label']} (target: {field['amo_target']}, field_id: {field.get('amo_field_id')})")
    except Exception as e:
        logger.error(f"Failed to load fields from amoCRM: {e}")
        raise RuntimeError(f"Failed to load fields from amoCRM: {e}")

    yield

    logger.info("Shutting down...")
    if 'polling_task' in locals():
        polling_task.cancel()


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
