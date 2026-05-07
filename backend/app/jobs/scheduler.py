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

    observation_jobs = [
        ("nws", settings.nws_alerts_enabled, settings.nws_alerts_interval_seconds),
        ("bluesky", settings.bluesky_enabled, settings.bluesky_interval_seconds),
        ("mastodon", settings.mastodon_enabled and bool(settings.mastodon_access_token), settings.mastodon_interval_seconds),
        ("acled", settings.acled_enabled and bool(settings.acled_api_key), settings.acled_interval_seconds),
    ]
    for source_name, enabled, interval in observation_jobs:
        if not enabled:
            continue
        from app.jobs.seed import run_observation_source_ingestion
        scheduler.add_job(
            run_observation_source_ingestion,
            "interval",
            seconds=interval,
            id=f"{source_name}_observation_ingestion",
            args=[source_name],
            replace_existing=True,
        )
        print(f"[scheduler] {source_name} observation ingestion registered (interval={interval}s).")

    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
