from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EvidenceItem, Observation
from app.schemas import EvidenceItemOut, MapSignalOut, ObservationOut
from app.services.scoring.hotspot import compute_hotspots
from app.services.intelligence import (
    dismiss_observation,
    eligible_map_signals,
    link_observation_to_event,
    promote_observation,
)

router = APIRouter(prefix="/observations", tags=["observations"])


def _observation_out(db: Session, observation: Observation) -> dict:
    evidence = db.get(EvidenceItem, observation.evidence_id)
    base = ObservationOut.model_validate(observation).model_dump()
    base["evidence"] = EvidenceItemOut.model_validate(evidence).model_dump() if evidence else None
    return base


@router.get("/", response_model=list[ObservationOut])
def list_observations(
    status: str | None = Query("lead"),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Observation)
    if status:
        query = query.filter(Observation.status == status)
    observations = query.order_by(Observation.created_at.desc()).limit(limit).all()
    return [_observation_out(db, observation) for observation in observations]


@router.get("/map-signals", response_model=list[MapSignalOut])
def list_map_signals(
    limit: int = Query(500, le=1000),
    db: Session = Depends(get_db),
):
    rows = []
    for signal in eligible_map_signals(db, limit=limit):
        base = _observation_out(db, signal["observation"])
        base["source_family"] = signal["source_family"]
        base["signal_weight"] = signal["signal_weight"]
        rows.append(base)
    return rows


@router.post("/{observation_id}/promote", response_model=ObservationOut)
def promote(observation_id: int, db: Session = Depends(get_db)):
    try:
        promote_observation(db, observation_id)
        compute_hotspots(db)
        observation = db.get(Observation, observation_id)
        db.commit()
        db.refresh(observation)
        return _observation_out(db, observation)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{observation_id}/dismiss", response_model=ObservationOut)
def dismiss(observation_id: int, db: Session = Depends(get_db)):
    try:
        observation = dismiss_observation(db, observation_id)
        db.commit()
        db.refresh(observation)
        return _observation_out(db, observation)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{observation_id}/link/{event_id}", response_model=ObservationOut)
def link(observation_id: int, event_id: int, db: Session = Depends(get_db)):
    try:
        link_observation_to_event(db, observation_id, event_id)
        compute_hotspots(db)
        observation = db.get(Observation, observation_id)
        db.commit()
        db.refresh(observation)
        return _observation_out(db, observation)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
