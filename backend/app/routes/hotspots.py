from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Hotspot
from app.schemas import HotspotOut

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.get("/", response_model=list[HotspotOut])
def list_hotspots(db: Session = Depends(get_db)):
    return db.query(Hotspot).order_by(Hotspot.priority_score.desc()).all()
