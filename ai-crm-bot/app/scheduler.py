from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .service import check_timeouts, process_crm_queue

scheduler = AsyncIOScheduler()


def start_scheduler(bot) -> None:
    scheduler.add_job(
        check_timeouts,
        trigger="interval",
        minutes=10,
        args=[bot],
    )
    scheduler.add_job(
        process_crm_queue,
        trigger="interval",
        minutes=settings.crm_retry_interval_minutes,
        args=[bot],
    )
    scheduler.start()