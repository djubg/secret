from fastapi import APIRouter

from app.services.update_service import UpdateService

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("/latest")
def latest_release():
    service = UpdateService()
    return service.latest()
