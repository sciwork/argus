import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from argus import config
from argus.kktix.report import send_report


logger = logging.getLogger(__name__)


def start_scheduler() -> BackgroundScheduler:
    """Start the daily report scheduler. Returns the scheduler so callers
    (e.g. the FastAPI lifespan) can shut it down on shutdown."""
    hour = config.settings.report_hour
    minute = config.settings.report_minute
    timezone = config.settings.report_timezone

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _run_report,
        CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id="daily_report",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Scheduler started: daily report at {hour:02d}:{minute:02d} ({timezone})"
    )
    return scheduler


def _run_report() -> None:
    try:
        send_report()
        logger.info("Daily report sent successfully")
    except Exception:
        logger.exception("Failed to send daily report")
