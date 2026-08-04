import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from .config import settings
from .db import init_db
from .handlers import router
from .scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

if not settings.telegram_bot_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler(bot)

    polling_task = asyncio.create_task(dp.start_polling(bot))

    yield

    polling_task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
    )