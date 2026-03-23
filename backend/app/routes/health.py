from datetime import datetime

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="ok",
        service="flashpoint",
        timestamp=datetime.utcnow().isoformat(),
    )
