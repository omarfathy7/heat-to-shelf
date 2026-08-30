from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.value_objects.thermal_observation import ThresholdStatus


class RiskResponse(BaseModel):
    shipment_id: UUID
    scenario_id: UUID | None = None
    score: float
    level: ThresholdStatus
    components: dict = {}
    peak_temperature_c: float | None = None
    time_above_threshold_hours: float = 0.0
    longest_persistence_hours: float = 0.0
    high_risk_segment_count: int = 0
    exposure_reduction_percent: float | None = None
    calculation_version: str
    explanation_factors: dict = {}
    created_at: datetime | None = None