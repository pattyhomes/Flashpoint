from fastapi import APIRouter

router = APIRouter(prefix="/priorities", tags=["priorities"])


@router.get("/")
def list_priorities():
    # TODO: implement priority ranking
    return []
