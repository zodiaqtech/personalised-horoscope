"""
APScheduler setup for midnight IST daily batch.

Schedule:  00:05 IST  →  18:35 UTC  (IST = UTC+5:30)
Cron expr: hour=18, minute=35  (UTC)

The scheduler runs inside the FastAPI process — no separate worker needed.
"""
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_scheduler: AsyncIOScheduler | None = None


async def _run_batch_wrapper():
    """Wrapper called by APScheduler — runs the full daily batch."""
    from app.services.batch_job import run_daily_batch
    logger.info("[Scheduler] Midnight IST cron triggered — starting daily batch")
    try:
        summary = await run_daily_batch()
        logger.info(
            f"[Scheduler] Batch complete: {summary['success']} ok, "
            f"{summary['errors']} errors, {summary['duration_seconds']}s"
        )
    except Exception as e:
        logger.error(f"[Scheduler] Batch job failed: {e}", exc_info=True)


def start_scheduler() -> AsyncIOScheduler:
    """
    Create and start the APScheduler with the midnight IST cron job.

    Cron schedule: 00:05 IST = 18:35 UTC
    APScheduler cron uses UTC by default.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")

    # 00:05 IST = 18:35 UTC (previous calendar day)
    # APScheduler CronTrigger with timezone='Asia/Kolkata' handles DST automatically
    _scheduler.add_job(
        _run_batch_wrapper,
        trigger=CronTrigger(
            hour=0,
            minute=5,
            timezone="Asia/Kolkata",  # APScheduler converts to UTC internally
        ),
        id="daily_horoscope_batch",
        name="Daily Horoscope Batch (00:05 IST)",
        replace_existing=True,
        misfire_grace_time=3600,  # If server was down, run up to 1 hour late
    )

    _scheduler.start()
    next_run = _scheduler.get_job("daily_horoscope_batch").next_run_time
    logger.info(f"[Scheduler] Started. Next batch run: {next_run.astimezone(IST).strftime('%Y-%m-%d %H:%M IST')}")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
