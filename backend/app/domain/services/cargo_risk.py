"""Pure, deterministic cargo-risk engine.

risk_score =
    w_peak       * peak_temperature_component
  + w_duration   * duration_component
  + w_persistence* persistence_component
  + w_high_risk  * high_risk_segment_component

Each component is normalized to 0..100 and the weighted sum clamped to 0..100.
Weights and bands are injected (from configuration), never scattered constants.
Application semantics only — never a claim a cargo is spoiled or safe to eat.
"""

from dataclasses import dataclass
from typing import Any

from app.domain.entities.product import ProductProfile
from app.domain.services.exposure import ExposureSummary, SegmentExposureInput
from app.domain.value_objects.thermal_observation import ThresholdStatus


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _rule_max_minutes(rules: dict[str, Any], key: str) -> float | None:
    rule = rules.get(key) or {}
    value = rule.get("max_minutes")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RiskWeights:
    peak_temperature: float
    duration: float
    persistence: float
    high_risk_segments: float

    @property
    def total(self) -> float:
        return sum((self.peak_temperature, self.duration, self.persistence, self.high_risk_segments))

    def normalized(self) -> "RiskWeights":
        total = self.total
        if total == 0:
            total = 1.0
        return RiskWeights(
            peak_temperature=self.peak_temperature / total,
            duration=self.duration / total,
            persistence=self.persistence / total,
            high_risk_segments=self.high_risk_segments / total,
        )


@dataclass(frozen=True)
class RiskBands:
    warning_at: float = 25.0
    high_at: float = 50.0
    critical_at: float = 75.0


@dataclass(frozen=True)
class RiskComponents:
    peak_temperature: float
    duration: float
    persistence: float
    high_risk_segments: float


@dataclass(frozen=True)
class RiskResult:
    score: float
    level: ThresholdStatus
    components: dict[str, float]
    peak_temperature_c: float | None
    time_above_threshold_hours: float
    longest_persistence_hours: float
    high_risk_segment_count: int
    explanation_factors: dict[str, Any]


def risk_level(score: float, bands: RiskBands) -> ThresholdStatus:
    if score >= bands.critical_at:
        return ThresholdStatus.CRITICAL
    if score >= bands.high_at:
        return ThresholdStatus.HIGH
    if score >= bands.warning_at:
        return ThresholdStatus.WARNING
    return ThresholdStatus.SAFE


def calculate_risk(
    exposure: ExposureSummary,
    profile: ProductProfile,
    weights: RiskWeights,
    bands: RiskBands,
    segment_inputs: list[SegmentExposureInput] | None = None,
) -> RiskResult:
    weights = weights.normalized()
    factors: dict[str, Any] = {}

    # --- peak temperature component ---
    peak = exposure.peak_temperature_c
    if peak is None:
        peak_component = 0.0
        factors["peak_temperature_missing"] = True
    else:
        span = max(profile.critical_threshold_c - profile.warning_threshold_c, 1e-9)
        peak_component = _clamp01((peak - profile.warning_threshold_c) / span) * 100.0

    # --- duration component ---
    duration_max = _rule_max_minutes(profile.exposure_rules, "duration")
    if duration_max is None or duration_max <= 0:
        duration_component = 0.0
        factors["duration_max_missing"] = True
    else:
        duration_component = _clamp01(exposure.total_duration_minutes / duration_max) * 100.0

    # --- persistence component ---
    persistence_max = _rule_max_minutes(profile.exposure_rules, "persistence")
    if persistence_max is None or persistence_max <= 0:
        persistence_component = 0.0
        factors["persistence_max_missing"] = True
    else:
        persistence_component = (
            _clamp01((exposure.longest_persistence_hours * 60.0) / persistence_max) * 100.0
        )

    # --- high-risk segment component ---
    denominator = exposure.total_segment_count or 1
    high_risk_component = _clamp01(exposure.high_risk_segment_count / denominator) * 100.0

    components = RiskComponents(
        peak_temperature=round(peak_component, 2),
        duration=round(duration_component, 2),
        persistence=round(persistence_component, 2),
        high_risk_segments=round(high_risk_component, 2),
    )
    score = round(
        min(
            100.0,
            max(
                0.0,
                weights.peak_temperature * components.peak_temperature
                + weights.duration * components.duration
                + weights.persistence * components.persistence
                + weights.high_risk_segments * components.high_risk_segments,
            ),
        ),
        2,
    )
    level = risk_level(score, bands)

    # Critical threshold override: if ANY segment has temperature >= critical_threshold,
    # force level to CRITICAL regardless of aggregated score.
    if segment_inputs is not None:
        for seg in segment_inputs:
            if seg.temperature_c is not None and seg.temperature_c >= profile.critical_threshold_c:
                level = ThresholdStatus.CRITICAL
                break

    factors["observed_segments"] = exposure.observed_segment_count
    factors["total_segments"] = exposure.total_segment_count
    if exposure.observed_segment_count == 0:
        factors["insufficient_observations"] = True

    return RiskResult(
        score=score,
        level=level,
        components={
            "peak_temperature": components.peak_temperature,
            "duration": components.duration,
            "persistence": components.persistence,
            "high_risk_segments": components.high_risk_segments,
        },
        peak_temperature_c=peak,
        time_above_threshold_hours=exposure.time_above_warning_hours,
        longest_persistence_hours=exposure.longest_persistence_hours,
        high_risk_segment_count=exposure.high_risk_segment_count,
        explanation_factors=factors,
    )