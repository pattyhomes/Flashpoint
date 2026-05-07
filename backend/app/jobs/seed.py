import json

from app.config import settings
from app.database import SessionLocal
from app.models import Event, EventSource, EvidenceItem, Hotspot, IngestRun, Observation
from app.services.ingestion.deduper import (
    find_matching_event,
    is_duplicate,
    is_syndicated_copy,
)
from app.services.ingestion.mock_source import MockSource
from app.services.intelligence import (
    apply_observation_automation,
    link_observation_to_event,
    record_evidence,
    record_observation,
)
from app.services.scoring.hotspot import compute_hotspots
from app.utils.time import utcnow_naive as utcnow

OBSERVATION_SOURCE_MAP = {
    "nws": ("nws", lambda: __import__("app.services.ingestion.nws_source", fromlist=["NwsAlertsSource"]).NwsAlertsSource()),
    "bluesky": ("bluesky", lambda: __import__("app.services.ingestion.bluesky_source", fromlist=["BlueskySource"]).BlueskySource()),
    "mastodon": ("mastodon", lambda: __import__("app.services.ingestion.mastodon_source", fromlist=["MastodonSource"]).MastodonSource()),
    "local_news": ("local_news", lambda: __import__("app.services.ingestion.local_news_source", fromlist=["LocalNewsSource"]).LocalNewsSource()),
    "acled": ("acled", lambda: __import__("app.services.ingestion.acled_source", fromlist=["AcledSource"]).AcledSource()),
}


def run_mock_ingestion():
    """Insert new mock events, skipping any already in the database.
    Called by the background scheduler — does not wipe existing data.
    Persists an IngestRun record for every attempt; updates it to success or failed."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()

    # Commit the run record before ingestion begins so it survives any failure.
    run = IngestRun(started_at=utcnow(), status="running", ingest_source="mock")
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
        run.finished_at = utcnow()
        run.events_inserted = inserted
        db.commit()
        print(f"[seed] Inserted {inserted} new mock events.")
        compute_hotspots(db)
    except Exception as e:
        db.rollback()  # undoes uncommitted event inserts; the IngestRun commit above is unaffected
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = utcnow()
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

    run = IngestRun(started_at=utcnow(), status="running", ingest_source="gdelt")
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

        before_evidence_count = db.query(EvidenceItem).count()
        before_observation_count = db.query(Observation).count()
        inserted = 0
        rejected = 0
        for event_schema in events:
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                rejected += 1
                continue
            evidence = record_evidence(
                db,
                source_type="gdelt",
                source_record_id=event_schema.source_id,
                source_url=event_schema.source_url,
                source_name="GDELT",
                source_title=event_schema.title,
                excerpt=event_schema.summary,
                published_at=event_schema.occurred_at,
                trust_tier="news",
                raw_payload_json=event_schema.raw_payload_json,
            )
            new_event = Event(**event_schema.model_dump())
            db.add(new_event)
            db.flush()
            db.add(EventSource(
                event_id=new_event.id,
                source_type="gdelt",
                source_record_id=event_schema.source_id,
                source_name="GDELT",
                source_url=event_schema.source_url,
                source_title=event_schema.title,
                source_published_at=event_schema.occurred_at,
                source_trust_weight=1.0,
                location_precision=event_schema.location_precision,
                metadata_json=event_schema.raw_payload_json,
            ))
            observation = record_observation(
                db,
                evidence=evidence,
                status="promoted",
                title=event_schema.title,
                summary=event_schema.summary,
                candidate_event_type=event_schema.event_type,
                latitude=event_schema.latitude,
                longitude=event_schema.longitude,
                city=event_schema.city,
                state=event_schema.state,
                country=event_schema.country,
                observed_at=event_schema.occurred_at,
                confidence_score=event_schema.confidence_score,
                severity_score=event_schema.severity_score,
                location_precision=event_schema.location_precision,
            )
            observation.promoted_event_id = new_event.id
            observation.linked_event_id = new_event.id
            inserted += 1
        db.commit()

        run.status = "success"
        run.finished_at = utcnow()
        run.events_inserted = inserted
        run.records_fetched = len(events)
        run.evidence_inserted = db.query(EvidenceItem).count() - before_evidence_count
        run.observations_inserted = db.query(Observation).count() - before_observation_count
        run.records_rejected = rejected
        run.reject_counts_json = json.dumps({"duplicate": rejected}, sort_keys=True, separators=(",", ":")) if rejected else "{}"
        db.commit()
        print(f"[gdelt] Inserted {inserted} new events.")
        compute_hotspots(db)
    except Exception as e:
        db.rollback()  # undoes uncommitted event inserts; the IngestRun commit above is unaffected
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = utcnow()
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
        started_at=utcnow(),
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

        before_evidence_count = db.query(EvidenceItem).count()
        before_observation_count = db.query(Observation).count()
        inserted = 0          # new events created
        corroborated = 0      # existing events corroborated
        syndicated = 0        # copies stored but not counted
        rejected = 0
        reject_counts: dict[str, int] = {}
        new_events_this_run = 0

        for event_schema, raw_article in article_pairs:
            # --- 1. Exact source_id dedup ---
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                rejected += 1
                reject_counts["duplicate"] = reject_counts.get("duplicate", 0) + 1
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

            evidence = record_evidence(
                db,
                source_type="eventregistry",
                source_record_id=er_uri,
                source_url=article_url,
                source_name=outlet_name,
                source_title=article_title or event_schema.title,
                excerpt=raw_article.get("body") or event_schema.summary,
                published_at=published_at,
                trust_tier="news",
                raw_payload=raw_article,
            )

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

                observation = record_observation(
                    db,
                    evidence=evidence,
                    status="lead",
                    title=event_schema.title,
                    summary=event_schema.summary,
                    candidate_event_type=event_schema.event_type,
                    latitude=event_schema.latitude,
                    longitude=event_schema.longitude,
                    city=event_schema.city,
                    state=event_schema.state,
                    country=event_schema.country,
                    observed_at=event_schema.occurred_at,
                    confidence_score=event_schema.confidence_score,
                    severity_score=event_schema.severity_score,
                    location_precision=event_schema.location_precision,
                )
                if syndicated_copy:
                    db.add(EventSource(
                        event_id=matched_event.id,
                        source_type="eventregistry",
                        source_record_id=er_uri,
                        source_name=outlet_name,
                        source_url=article_url,
                        source_title=article_title,
                        source_published_at=published_at,
                        source_trust_weight=0.0,
                        location_precision=event_schema.location_precision,
                        metadata_json=event_schema.raw_payload_json,
                    ))
                    observation.status = "linked"
                    observation.linked_event_id = matched_event.id
                    observation.updated_at = utcnow()
                    syndicated += 1
                else:
                    before_count = matched_event.source_count or 1
                    link_observation_to_event(db, observation.id, matched_event.id)
                    if (matched_event.source_count or 1) > before_count:
                        corroborated += 1
                        print(
                            f"[eventregistry] Corroborated event #{matched_event.id}: "
                            f"'{matched_event.title[:60]}' (+1 source family)"
                        )

            else:
                # --- Discovery path ---
                if not settings.event_registry_create_new_events:
                    observation = record_observation(
                        db,
                        evidence=evidence,
                        status="lead",
                        title=event_schema.title,
                        summary=event_schema.summary,
                        candidate_event_type=event_schema.event_type,
                        latitude=event_schema.latitude,
                        longitude=event_schema.longitude,
                        city=event_schema.city,
                        state=event_schema.state,
                        country=event_schema.country,
                        observed_at=event_schema.occurred_at,
                        confidence_score=event_schema.confidence_score,
                        severity_score=event_schema.severity_score,
                        location_precision=event_schema.location_precision,
                    )
                    apply_observation_automation(db, observation)
                    continue
                if new_events_this_run >= settings.event_registry_max_new_events_per_run:
                    observation = record_observation(
                        db,
                        evidence=evidence,
                        status="lead",
                        title=event_schema.title,
                        summary=event_schema.summary,
                        candidate_event_type=event_schema.event_type,
                        latitude=event_schema.latitude,
                        longitude=event_schema.longitude,
                        city=event_schema.city,
                        state=event_schema.state,
                        country=event_schema.country,
                        observed_at=event_schema.occurred_at,
                        confidence_score=event_schema.confidence_score,
                        severity_score=event_schema.severity_score,
                        location_precision=event_schema.location_precision,
                    )
                    apply_observation_automation(db, observation)
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

                observation = record_observation(
                    db,
                    evidence=evidence,
                    status="promoted",
                    title=event_schema.title,
                    summary=event_schema.summary,
                    candidate_event_type=event_schema.event_type,
                    latitude=event_schema.latitude,
                    longitude=event_schema.longitude,
                    city=event_schema.city,
                    state=event_schema.state,
                    country=event_schema.country,
                    observed_at=event_schema.occurred_at,
                    confidence_score=capped_confidence,
                    severity_score=event_schema.severity_score,
                    location_precision=event_schema.location_precision,
                )
                observation.promoted_event_id = new_event.id
                observation.linked_event_id = new_event.id

                inserted += 1
                new_events_this_run += 1
                print(
                    f"[eventregistry] New event: '{event_schema.title[:60]}' "
                    f"(confidence={capped_confidence}, precision={event_schema.location_precision})"
                )

        db.commit()

        run = db.get(IngestRun, run_id)
        run.status = "success"
        run.finished_at = utcnow()
        run.events_inserted = inserted
        run.records_fetched = len(article_pairs)
        run.evidence_inserted = db.query(EvidenceItem).count() - before_evidence_count
        run.observations_inserted = db.query(Observation).count() - before_observation_count
        run.records_rejected = rejected
        run.reject_counts_json = json.dumps(reject_counts, sort_keys=True, separators=(",", ":"))
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
        run.finished_at = utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[eventregistry] Error: {e}")
    finally:
        db.close()


def run_observation_source_ingestion(source_name: str):
    """Fetch weak/context observation sources into the review queue.

    These sources never create Events directly. They only write EvidenceItem and
    Observation rows for operator review or contextual awareness.
    """
    if source_name not in OBSERVATION_SOURCE_MAP:
        raise ValueError(f"Unknown observation source: {source_name}")

    ingest_source, factory = OBSERVATION_SOURCE_MAP[source_name]
    db = SessionLocal()
    run = IngestRun(started_at=utcnow(), status="running", ingest_source=ingest_source)
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    try:
        source = factory()
        candidates = source.fetch()
        stats = getattr(source, "stats", {}) or {}
        before_evidence_count = db.query(EvidenceItem).count()
        before_count = db.query(Observation).count()
        confirmed_changed = False
        for candidate in candidates:
            evidence = record_evidence(
                db,
                source_type=candidate.source_type,
                source_record_id=candidate.source_record_id,
                source_url=candidate.source_url,
                source_name=candidate.source_name,
                source_title=candidate.source_title,
                excerpt=candidate.excerpt,
                published_at=candidate.published_at,
                trust_tier=candidate.trust_tier,
                raw_payload=candidate.raw_payload,
            )
            observation = record_observation(
                db,
                evidence=evidence,
                status=candidate.status,
                title=candidate.title,
                summary=candidate.summary,
                candidate_event_type=candidate.candidate_event_type,
                latitude=candidate.latitude,
                longitude=candidate.longitude,
                city=candidate.city,
                state=candidate.state,
                country=candidate.country,
                observed_at=candidate.observed_at,
                confidence_score=candidate.confidence_score,
                severity_score=candidate.severity_score,
                location_precision=candidate.location_precision,
                location_confidence=candidate.location_confidence,
                location_reason=candidate.location_reason,
                exception_category=candidate.exception_category,
                exception_detail=candidate.exception_detail,
            )
            if apply_observation_automation(db, observation) is not None:
                confirmed_changed = True

        db.commit()
        inserted = db.query(Observation).count() - before_count
        run = db.get(IngestRun, run_id)
        run.status = "success"
        run.finished_at = utcnow()
        run.events_inserted = inserted
        run.records_fetched = int(stats.get("fetched", len(candidates)))
        run.evidence_inserted = db.query(EvidenceItem).count() - before_evidence_count
        run.observations_inserted = inserted
        run.records_rejected = int(stats.get("rejected", 0))
        run.reject_counts_json = json.dumps(stats.get("reject_counts", {}), sort_keys=True, separators=(",", ":"))
        db.commit()
        if confirmed_changed:
            compute_hotspots(db)
        print(f"[{ingest_source}] Recorded {inserted} observation(s).")
    except Exception as e:
        db.rollback()
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[{ingest_source}] Error: {e}")
    finally:
        db.close()


def reset_and_seed():
    """Wipe all events and hotspots, reseed from scratch, then compute hotspot scores.
    Safe to rerun — always produces a clean, consistent dataset."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()
    try:
        db.query(EventSource).delete()
        db.query(Observation).delete()
        db.query(EvidenceItem).delete()
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
