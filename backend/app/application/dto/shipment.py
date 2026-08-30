from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.domain.entities.shipment import ShipmentStatus
from app.domain.value_objects.place import PlaceInput


class CreateShipmentRequest(BaseModel):
    product_id: UUID
    origin: PlaceInput
    destination: PlaceInput
    departure_time: datetime

    @field_validator("departure_time")
    @classmethod
    def _departure_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("departure_time must be timezone-aware")
        return value.astimezone(timezone.utc)


class ShipmentResponse(BaseModel):
    id: UUID
    product_id: UUID
    origin: dict
    destination: dict
    departure_time_utc: datetime
    status: ShipmentStatus
    estimated_duration_seconds: int | None = None
    distance_meters: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None