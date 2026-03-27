from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings

scheduler = BackgroundScheduler()


def start_scheduler():
    """Register background jobs and start the scheduler."""
    if settings.ingest_source == "gdelt":
        from app.jobs.seed import run_gdelt_ingestion
        scheduler.add_job(
            run_gdelt_ingestion,
            "interval",
            seconds=settings.ingestion_interval_seconds,
            id="gdelt_ingestion",
            replace_existing=True,
        )
    elif settings.mock_data_enabled:
        from app.jobs.seed import run_mock_ingestion
        scheduler.add_job(
            run_mock_ingestion,
            "interval",
            seconds=settings.ingestion_interval_seconds,
            id="mock_ingestion",
            replace_existing=True,
        )

    # Event Registry — supplementary source; runs alongside the primary source
    if settings.event_registry_enabled and settings.event_registry_api_key:
        from app.jobs.seed import run_eventregistry_ingestion
        scheduler.add_job(
            run_eventregistry_ingestion,
            "interval",
            seconds=settings.event_registry_interval_seconds,
            id="eventregistry_ingestion",
            replace_existing=True,
        )
        print(
            f"[scheduler] Event Registry ingestion registered "
            f"(interval={settings.event_registry_interval_seconds}s)."
        )

    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
