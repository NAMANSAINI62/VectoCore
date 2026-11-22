from fastapi import APIRouter, status
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["Health"])

@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health Check",
    description="Check connectivity and health status",
)
async def get_health() -> HealthResponse:
    return await HealthService.get_system_health()
