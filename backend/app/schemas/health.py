"""Health check response schemas."""

from typing import Literal
from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    """Health status for a dependent subsystem."""

    connected: bool = Field(..., description="Whether the connection to the service succeeded")
    status: Literal["healthy", "unhealthy", "not_configured", "unavailable"] = Field(..., description="Normalized health state")


class HealthResponse(BaseModel):
    """Structured response for API health checks."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ..., description="Overall system health status"
    )
    version: str = Field(..., description="API Version")
    environment: str = Field(..., description="Current running environment")
    database: ServiceHealth = Field(..., description="PostgreSQL status")
