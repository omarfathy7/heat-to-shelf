"""Deterministic recommendation builder (pure).

The recommendation is a comparison report over the ranked scenarios and
the original baseline. Every number comes from the risk engine; the LLM,
whenever added, may only paraphrase this result.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.services.scenario_comparison import (
    ScenarioOutcome,
    exposure_reduction_percent,
    is_level_improved,
)
from app.domain.value_objects.thermal_observation import ThresholdStatus


@dataclass(frozen=True)
class RecommendationDraft:
    recommended_scenario_id: UUID | None
    recommended_departure_time_utc: datetime
    reason_codes: list[str]
    explanation_factors: dict
    original_score: float
    recommended_score: float
    exposure_reduction_percent: float
    original_level: ThresholdStatus
    recommended_level: ThresholdStatus

    @property
    def recommended(self) -> bool:
        return self.recommended_score < self.original_score


_COMPONENT_REASONS = {
    "peak_temperature": "lower_peak_temperature",
    "duration": "less_time_above_threshold",
    "persistence": "lower_persistence",
    "high_risk_segments": "fewer_high_risk_segments",
}


def build_recommendation(
    *,
    original: ScenarioOutcome,
    recommended: ScenarioOutcome,
) -> RecommendationDraft:
    """Compare the ranked-best scenario against the original baseline."""
    codes: list[str] = []
    if recommended.score < original.score:
        codes.append("lower_risk_score")
    deltas: dict[str, float] = {}
    for component, code in _COMPONENT_REASONS.items():
        before = original.components.get(component, 0.0)
        after = recommended.components.get(component, 0.0)
        deltas[component] = round(before - after, 2)
        if after < before:
            codes.append(code)

    reduction = exposure_reduction_percent(original.score, recommended.score)
    factors = {
        "original_score": original.score,
        "recommended_score": recommended.score,
        "exposure_reduction_percent": reduction,
        "original_level": original.level.value,
        "recommended_level": recommended.level.value,
        "level_improved": is_level_improved(original.level, recommended.level),
        "component_deltas_before_minus_after": deltas,
    }
    return RecommendationDraft(
        recommended_scenario_id=recommended.id,
        recommended_departure_time_utc=recommended.departure_time_utc,
        reason_codes=codes,
        explanation_factors=factors,
        original_score=original.score,
        recommended_score=recommended.score,
        exposure_reduction_percent=reduction,
        original_level=original.level,
        recommended_level=recommended.level,
    )