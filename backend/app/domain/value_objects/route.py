from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.coordinates import Coordinate


class RouteData(BaseModel):
    """Normalized route returned by any RoutingProvider."""

    provider: str
    provider_route_id: str | None = None
    geometry: list[Coordinate]
    distance_meters: int
    duration_seconds: int
    raw_response_ref: str | None = None
    metadata: dict[str, Any] = {}

    @field_validator("geometry")
    @classmethod
    def _geometry_valid(cls, value: list[Coordinate]) -> list[Coordinate]:
        if len(value) < 2:
            raise AppError(
                ErrorCode.ROUTING_PROVIDER_FAILED,
                "route geometry must contain at least two points",
            )
        return value

    @field_validator("distance_meters")
    @classmethod
    def _distance_positive(cls, value: int) -> int:
        if value <= 0:
            raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "route distance must be positive")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def _duration_positive(cls, value: int) -> int:
        if value <= 0:
            raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "route duration must be positive")
        return value


class RouteSegment(BaseModel):
    sequence: int
    geometry: list[Coordinate]
    start_distance_meters: float
    end_distance_meters: float
    estimated_arrival_utc: datetime
    duration_seconds: int

    @field_validator("geometry")
    @classmethod
    def _geometry_valid(cls, value: list[Coordinate]) -> list[Coordinate]:
        if len(value) < 2:
            raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "segment geometry must have at least two points")
        return value