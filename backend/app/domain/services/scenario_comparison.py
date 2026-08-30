"""Deterministic scenario ranking (pure).

Lower risk score is better. Ties break on the earlier departure time so
the ranking is fully reproducible. Sourced scenarios carry an id and a
departure time; ranking never touches the provider or the database.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.value_objects.thermal_observation import ThresholdStatus

LEVEL_SEVERITY = {
    ThresholdStatus.UNKNOWN: 0,
    ThresholdStatus.SAFE: 1,
    ThresholdStatus.WARNING: 2,
    ThresholdStatus.HIGH: 3,
    ThresholdStatus.CRITICAL: 4,
}


@dataclass(frozen=True)
class ScenarioOutcome:
    """Ranking surface produced by the risk engine for one departure time."""

    id: UUID | None
    departure_time_utc: datetime
    score: float
    level: ThresholdStatus
    components: dict[str, float]
    peak_temperature_c: float | None
    time_above_threshold_hours: float
    longest_persistence_hours: float
    high_risk_segment_count: int
    rank: int | None = None


def rank_scenarios(outcomes: list[ScenarioOutcome]) -> list[ScenarioOutcome]:
    """Sort ascending by (score, departure_time_utc) and assign 1-based ranks."""
    ordered = sorted(outcomes, key=lambda o: (o.score, o.departure_time_utc))
    return [
        ScenarioOutcome(
            id=o.id,
            departure_time_utc=o.departure_time_utc,
            score=o.score,
            level=o.level,
            components=o.components,
            peak_temperature_c=o.peak_temperature_c,
            time_above_threshold_hours=o.time_above_threshold_hours,
            longest_persistence_hours=o.longest_persistence_hours,
            high_risk_segment_count=o.high_risk_segment_count,
            rank=index + 1,
        )
        for index, o in enumerate(ordered)
    ]


def exposure_reduction_percent(original_score: float, recommended_score: float) -> float:
    """Percentage improvement over the original score; zero original -> 0.0."""
    if original_score <= 0:
        return 0.0
    return round((original_score - recommended_score) / original_score * 100.0, 4)


def is_level_improved(before: ThresholdStatus, after: ThresholdStatus) -> bool:
    return LEVEL_SEVERITY[after] < LEVEL_SEVERITY[before]