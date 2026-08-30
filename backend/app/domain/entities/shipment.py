from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.value_objects.place import Place

SHIPMENT_STATUS_VALUES = ("draft", "routing", "analyzing", "ready", "failed")


class ShipmentStatus(str, Enum):
    DRAFT = "draft"
    ROUTING = "routing"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class Shipment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    user_id: UUID
    product_profile_id: UUID
    origin: Place
    destination: Place
    departure_time_utc: datetime
    status: ShipmentStatus = ShipmentStatus.DRAFT
    estimated_duration_seconds: int | None = None
    distance_meters: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None