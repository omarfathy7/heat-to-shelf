from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.value_objects.thermal_observation import ThresholdStatus

_LEVELS = frozenset(
    {ThresholdStatus.SAFE, ThresholdStatus.WARNING, ThresholdStatus.HIGH, ThresholdStatus.CRITICAL}
)


class RiskAssessment(BaseModel):
    """Deterministic, versioned cargo-risk result. Application semantics only."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    shipment_id: UUID
    scenario_id: UUID | None = None
    score: float
    level: ThresholdStatus
    peak_temperature_c: float | None = None
    time_above_threshold_hours: float = 0.0
    longest_persistence_hours: float = 0.0
    high_risk_segment_count: int = 0
    exposure_reduction_percent: float | None = None
    calculation_version: str
    inputs_snapshot: dict[str, Any] = {}
    explanation_factors: dict[str, Any] = {}
    created_at: datetime | None = None

    @field_validator("score")
    @classmethod
    def _score_in_band(cls, value: float) -> float:
        if not (0.0 <= value <= 100.0):
            raise ValueError("score must be within 0..100")
        return value

    @field_validator("level")
    @classmethod
    def _level_supported(cls, value: ThresholdStatus) -> ThresholdStatus:
        if value not in _LEVELS:
            raise ValueError("risk level must be safe|warning|high|critical")
        return value