import json
from datetime import datetime

from app.config import settings
from app.database import SessionLocal
from app.models import Event, EventSource, Hotspot, IngestRun
from app.services.ingestion.deduper import (
    find_matching_event,
    is_duplicate,
    is_syndicated_copy,
)
from app.services.ingestion.mock_source import MockSource
from app.services.scoring.hotspot import compute_hotspots


def run_mock_ingestion():
    """Insert new mock events, skipping any already in the database.
    Called by the background scheduler — does not wipe existing data.
    Persists an IngestRun record for every attempt; updates it to success or failed."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()

    # Commit the run record before ingestion begins so it survives any failure.
    run = IngestRun(started_at=datetime.utcnow(), status="running", ingest_source="mock")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    try:
        inserted = 0
        for event_schema in events:
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                continue
            db.add(Event(**event_schema.model_dump()))
            inserted += 1
        db.commit()

        run.status = "success"
        run.finished_at = datetime.utcnow()
        run.events_inserted = inserted
        db.commit()
        print(f"[seed] Inserted {inserted} new mock events.")
        compute_hotspots(db)
    except Exception as e:
        db.rollback()  # undoes uncommitted event inserts; the IngestRun commit above is unaffected
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[seed] Error: {e}")
    finally:
        db.close()


def run_gdelt_ingestion():
    """Fetch real events from GDELT 2.0, deduplicate, and store.
    Uses a source-aware checkpoint so GDELT and mock run histories stay separate.
    Persists an IngestRun record for every attempt; updates it to success or failed."""
    from app.services.ingestion.gdelt_source import GdeltSource

    db = SessionLocal()

    run = IngestRun(started_at=datetime.utcnow(), status="running", ingest_source="gdelt")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    try:
        # Source-aware checkpoint: last successful GDELT run ordered by finished_at
        last_success = (
            db.query(IngestRun)
            .filter(IngestRun.ingest_source == "gdelt", IngestRun.status == "success")
            .order_by(IngestRun.finished_at.desc())
            .first()
        )
        since = last_success.finished_at if last_success else None

        events = GdeltSource().fetch(since=since)

        inserted = 0
        for event_schema in events:
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                continue
            db.add(Event(**event_schema.model_dump()))
            inserted += 1
        db.commit()

        run.status = "success"
        run.finished_at = datetime.utcnow()
        run.events_inserted = inserted
        db.commit()
        print(f"[gdelt] Inserted {inserted} new events.")
        compute_hotspots(db)
    except Exception as e:
        db.rollback()  # undoes uncommitted event inserts; the IngestRun commit above is unaffected
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[gdelt] Error: {e}")
    finally:
        db.close()


def run_eventregistry_ingestion():
    """Fetch Event Registry articles, corroborate existing events, and optionally discover new ones.

    Corroboration path (always active):
      Matches ER articles against existing events using location + time + title similarity.
      Independent matches → add EventSource record, increment source_count, uplift confidence.
      Syndicated copies   → add EventSource with weight=0, no uplift.

    Discovery path (requires EVENT_REGISTRY_CREATE_NEW_EVENTS=true):
      Novel articles that don't match any existing event are inserted as new events,
      subject to MAX_NEW_EVENTS_PER_RUN and tiered uncorroborated confidence caps.

    Records an IngestRun for every attempt.
    """
    from app.services.ingestion.eventregistry_source import (
        EventRegistrySource,
        _apply_uncorroborated_cap,
    )

    db = SessionLocal()

    run = IngestRun(
        started_at=datetime.utcnow(),
        status="running",
        ingest_source="eventregistry",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    try:
        source = EventRegistrySource()
        article_pairs = source.fetch()  # list of (EventCreate, raw_article)

        inserted = 0          # new events created
        corroborated = 0      # existing events corroborated
        syndicated = 0        # copies stored but not counted
        new_events_this_run = 0

        for event_schema, raw_article in article_pairs:
            # --- 1. Exact source_id dedup ---
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                continue

            er_uri       = event_schema.source_id  # "er-{uri}"
            outlet_name  = (raw_article.get("source") or {}).get("title") or None
            article_url  = raw_article.get("url") or None
            article_title = raw_article.get("title") or None
            published_at  = event_schema.occurred_at
            try:
                meta = json.loads(event_schema.raw_payload_json or "{}")
                er_event_uri = meta.get("er_event_uri")
            except Exception:
                er_event_uri = None

            # --- 2. Cross-source match ---
            matched_event = find_matching_event(
                title=event_schema.title,
                lat=event_schema.latitude,
                lon=event_schema.longitude,
                occurred_at=event_schema.occurred_at,
                event_type=event_schema.event_type,
                db=db,
            )

            if matched_event is not None:
                # --- Corroboration path ---
                # Load existing sources for this event
                existing_sources = (
                    db.query(EventSource)
                    .filter(EventSource.event_id == matched_event.id)
                    .all()
                )

                syndicated_copy = is_syndicated_copy(
                    outlet_name=outlet_name,
                    article_url=article_url,
                    article_title=article_title,
                    article_published_at=published_at,
                    article_er_event_uri=er_event_uri,
                    existing_sources=existing_sources,
                )

                trust_weight = 0.0 if syndicated_copy else 1.0

                db.add(EventSource(
                    event_id=matched_event.id,
                    source_type="eventregistry",
                    source_record_id=er_uri,
                    source_name=outlet_name,
                    source_url=article_url,
                    source_title=article_title,
                    source_published_at=published_at,
                    source_trust_weight=trust_weight,
                    location_precision=event_schema.location_precision,
                    metadata_json=event_schema.raw_payload_json,
                ))

                if not syndicated_copy:
                    # Independent corroborating source: increment count, uplift confidence
                    matched_event.source_count = (matched_event.source_count or 1) + 1
                    matched_event.confidence_score = round(
                        min(1.0, (matched_event.confidence_score or 0.0) + 0.08), 3
                    )
                    corroborated += 1
                    print(
                        f"[eventregistry] Corroborated event #{matched_event.id}: "
                        f"'{matched_event.title[:60]}' (+1 source)"
                    )
                else:
                    syndicated += 1

            else:
                # --- Discovery path ---
                if not settings.event_registry_create_new_events:
                    continue
                if new_events_this_run >= settings.event_registry_max_new_events_per_run:
                    continue

                # Apply tiered uncorroborated confidence cap
                capped_confidence = _apply_uncorroborated_cap(
                    confidence=event_schema.confidence_score,
                    precision=event_schema.location_precision or "city",
                    max_cap=settings.event_registry_max_confidence_uncorroborated,
                )

                # Build and insert the new event
                event_data = event_schema.model_dump()
                event_data["confidence_score"] = capped_confidence
                new_event = Event(**event_data)
                db.add(new_event)
                db.flush()  # get ID for the EventSource FK

                db.add(EventSource(
                    event_id=new_event.id,
                    source_type="eventregistry",
                    source_record_id=er_uri,
                    source_name=outlet_name,
                    source_url=article_url,
                    source_title=article_title,
                    source_published_at=published_at,
                    source_trust_weight=1.0,
                    location_precision=event_schema.location_precision,
                    metadata_json=event_schema.raw_payload_json,
                ))

                inserted += 1
                new_events_this_run += 1
                print(
                    f"[eventregistry] New event: '{event_schema.title[:60]}' "
                    f"(confidence={capped_confidence}, precision={event_schema.location_precision})"
                )

        db.commit()

        run = db.get(IngestRun, run_id)
        run.status = "success"
        run.finished_at = datetime.utcnow()
        run.events_inserted = inserted
        db.commit()

        print(
            f"[eventregistry] Done — "
            f"{inserted} new events, {corroborated} corroborated, {syndicated} syndicated."
        )
        compute_hotspots(db)

    except Exception as e:
        db.rollback()
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[eventregistry] Error: {e}")
    finally:
        db.close()


def reset_and_seed():
    """Wipe all events and hotspots, reseed from scratch, then compute hotspot scores.
    Safe to rerun — always produces a clean, consistent dataset."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()
    try:
        db.query(Hotspot).delete()
        db.query(Event).delete()
        db.commit()

        for event_schema in events:
            db.add(Event(**event_schema.model_dump()))

        db.commit()
        print(f"[seed] Seeded {len(events)} events.")

        compute_hotspots(db)
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()
