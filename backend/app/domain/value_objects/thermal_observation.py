from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

THRESHOLD_STATUS_VALUES = ("safe", "warning", "high", "critical", "unknown")


class ThresholdStatus(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ThermalObservation(BaseModel):
    """One normalized observation per segment/time sample."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    segment_id: UUID
    observed_at_utc: datetime | None = None
    latitude: float
    longitude: float
    temperature_c: float | None = None
    threshold_status: ThresholdStatus = ThresholdStatus.UNKNOWN
    exceedance_hours: float | None = None
    persistence_hours: float | None = None
    relative_humidity: float | None = None
    wet_bulb_temp_c: float | None = None
    solar_irradiance_w: float | None = None
    source: str = "fortyguard"
    source_request_hash: str = ""
    data_quality: dict[str, Any] = {}