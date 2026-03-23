from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "flashpoint",
        "timestamp": datetime.utcnow().isoformat(),
    }
