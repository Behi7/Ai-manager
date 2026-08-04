from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .service import check_timeouts

scheduler = AsyncIOScheduler()


def start_scheduler(bot) -> None:
    scheduler.add_job(
        check_timeouts,
        trigger="interval",
        minutes=10,
        args=[bot],
    )
    scheduler.start()