from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.entities.shipment import ShipmentStatus
from app.domain.value_objects.thermal_observation import ThresholdStatus


class AnalyzeResponse(BaseModel):
    shipment_id: UUID
    status: ShipmentStatus
    developed_segments: int
    observed_segments: int
    error_code: str | None = None
    error_message: str | None = None


class ObservationResponse(BaseModel):
    temperature_c: float | None = None
    observed_at_utc: datetime | None = None
    threshold_status: ThresholdStatus
    latitude: float
    longitude: float
    source: str
    source_request_hash: str
    data_quality: dict


class JourneySegmentResponse(BaseModel):
    sequence: int
    start_distance_meters: float
    end_distance_meters: float
    estimated_arrival_utc: datetime
    duration_seconds: int
    midpoint: dict
    observation: ObservationResponse | None = None


class ThermalJourneyResponse(BaseModel):
    shipment_id: UUID
    status: ShipmentStatus
    segments: list[JourneySegmentResponse]
    geojson: dict