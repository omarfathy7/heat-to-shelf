from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.application.dto.risk import RiskResponse
from app.domain.entities.scenario import ScenarioStatus
from app.domain.value_objects.thermal_observation import ThresholdStatus


class ScenarioRequest(BaseModel):
    departure_times: list[datetime]

    @field_validator("departure_times")
    @classmethod
    def _departures_normalized(cls, value: list[datetime]) -> list[datetime]:
        if not value:
            raise ValueError("departure_times must not be empty")
        normalized = []
        for departure in value:
            if departure.tzinfo is None or departure.utcoffset() is None:
                raise ValueError("each departure time must be timezone-aware")
            normalized.append(departure.astimezone(timezone.utc))
        if len(set(normalized)) != len(normalized):
            raise ValueError("departure_times must be unique")
        return normalized


class ScenarioResultResponse(BaseModel):
    id: UUID
    departure_time_utc: datetime
    status: ScenarioStatus
    rank: int | None = None
    is_recommended: bool = False
    score: float | None = None
    level: ThresholdStatus | None = None
    components: dict = {}
    peak_temperature_c: float | None = None
    time_above_threshold_hours: float = 0.0
    longest_persistence_hours: float = 0.0
    high_risk_segment_count: int = 0


class RecommendationResponse(BaseModel):
    id: UUID | None = None
    shipment_id: UUID
    recommended_scenario_id: UUID
    recommended_departure_time_utc: datetime
    original_score: float
    recommended_score: float
    exposure_reduction_percent: float
    original_level: ThresholdStatus
    recommended_level: ThresholdStatus
    level_improved: bool
    reason_codes: list[str]
    explanation_factors: dict
    created_at: datetime | None = None


class ScenarioRunResponse(BaseModel):
    shipment_id: UUID
    baseline: RiskResponse
    scenarios: list[ScenarioResultResponse]
    recommendation: RecommendationResponse