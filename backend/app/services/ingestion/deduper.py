from sqlalchemy.orm import Session

from app.models import Event


def is_duplicate(source_id: str, db: Session) -> bool:
    """Return True if an event with this source_id already exists in the database."""
    if not source_id:
        return False
    return db.query(Event).filter(Event.source_id == source_id).first() is not None
