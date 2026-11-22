"""Service layer for aggregating system health."""
from app.config.settings import get_settings
from app.database.session import check_database_health
from app.schemas.health import HealthResponse, ServiceHealth

settings = get_settings()


class HealthService:
    """Service to evaluate backend and database health."""

    @staticmethod
    async def get_system_health() -> HealthResponse:
        """Report primary database connectivity for the chatbot foundation."""
        db_healthy = await check_database_health()
        overall = "healthy" if db_healthy else "unhealthy"

        return HealthResponse(
            status=overall,
            version="1.0.0",
            environment=settings.APP_ENV,
            database=ServiceHealth(
                connected=db_healthy,
                status="healthy" if db_healthy else "unhealthy",
            ),
        )
