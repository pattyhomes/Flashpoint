from fastapi import APIRouter

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.get("/")
def list_hotspots():
    # TODO: implement hotspot scoring
    return []
