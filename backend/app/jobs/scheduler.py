from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings

scheduler = BackgroundScheduler()


def start_scheduler():
    """Register background jobs and start the scheduler."""
    if settings.mock_data_enabled:
        from app.jobs.seed import run_mock_ingestion
        scheduler.add_job(
            run_mock_ingestion,
            "interval",
            seconds=settings.ingestion_interval_seconds,
            id="mock_ingestion",
            replace_existing=True,
        )

    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
