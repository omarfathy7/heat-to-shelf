from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.entities.product import ProductProfile
from app.domain.services.cargo_risk import (
    RiskBands,
    RiskWeights,
    calculate_risk,
    risk_level,
)
from app.domain.services.exposure import ExposureSummary, SegmentExposureInput, compute_exposure
from app.domain.value_objects.thermal_observation import ThresholdStatus

WEIGHTS = RiskWeights(peak_temperature=0.55, duration=0.45, persistence=0.0, high_risk_segments=0.0)
BANDS = RiskBands(warning_at=25.0, high_at=50.0, critical_at=75.0)
EXPOSURE_RULES = {
    "duration": {"max_minutes": 1440},
    "exceedance": {"max_minutes": 60},
    "persistence": {"max_minutes": 30},
}


def profile(**overrides) -> ProductProfile:
    base = dict(
        id=uuid4(),
        product_id=uuid4(),
        version=1,
        min_temp_c=0.0,
        max_temp_c=4.0,
        warning_threshold_c=8.0,
        critical_threshold_c=12.0,
        exposure_rules=EXPOSURE_RULES,
        source_name="Test",
        source_url="https://example.com/source",
        effective_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return ProductProfile(**base)


def segments(statuses: list[tuple[ThresholdStatus, int]]) -> list[SegmentExposureInput]:
    return [
        SegmentExposureInput(sequence=i + 1, status=status, duration_seconds=duration)
        for i, (status, duration) in enumerate(statuses)
    ]


class TestRiskLevel:
    def test_band_boundaries(self) -> None:
        assert risk_level(0.0, BANDS) == ThresholdStatus.SAFE
        assert risk_level(24.0, BANDS) == ThresholdStatus.SAFE
        assert risk_level(25.0, BANDS) == ThresholdStatus.WARNING
        assert risk_level(49.0, BANDS) == ThresholdStatus.WARNING
        assert risk_level(50.0, BANDS) == ThresholdStatus.HIGH
        assert risk_level(74.0, BANDS) == ThresholdStatus.HIGH
        assert risk_level(75.0, BANDS) == ThresholdStatus.CRITICAL
        assert risk_level(100.0, BANDS) == ThresholdStatus.CRITICAL


class TestCalculateRisk:
    def test_peak_component_boundaries(self) -> None:
        # peak == warning threshold -> 0; peak == critical -> 100
        low = calculate_risk(
            compute_exposure(
                [SegmentExposureInput(1, ThresholdStatus.WARNING, 3600, temperature_c=8.0)]
            ),
            profile(),
            WEIGHTS,
            BANDS,
        )
        assert low.components["peak_temperature"] <= 0.01

        critical = calculate_risk(
            compute_exposure(
                [SegmentExposureInput(1, ThresholdStatus.CRITICAL, 3600, temperature_c=12.0)]
            ),
            profile(),
            WEIGHTS,
            BANDS,
        )
        assert critical.components["peak_temperature"] == 100.0

    def test_duration_component_matches_rule(self) -> None:
        half = calculate_risk(
            compute_exposure(segments([(ThresholdStatus.SAFE, 720 * 60)])),  # 720 min
            profile(),
            WEIGHTS,
            BANDS,
        )
        assert half.components["duration"] == pytest.approx(50.0, abs=0.01)

    def test_persistence_component_matches_rule(self) -> None:
        # longest run 30 min = persistence max -> 100
        run = calculate_risk(
            compute_exposure(segments([(ThresholdStatus.HIGH, 30 * 60)])),
            profile(),
            WEIGHTS,
            BANDS,
        )
        assert run.components["persistence"] == pytest.approx(100.0, abs=0.01)

    def test_high_risk_segment_component_ratio(self) -> None:
        exp = compute_exposure(
            [
                SegmentExposureInput(1, ThresholdStatus.HIGH, 600),
                SegmentExposureInput(2, ThresholdStatus.SAFE, 600),
                SegmentExposureInput(3, ThresholdStatus.CRITICAL, 600),
                SegmentExposureInput(4, ThresholdStatus.SAFE, 600),
                SegmentExposureInput(5, ThresholdStatus.SAFE, 600),
            ]
        )
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.HIGH, 600),
            SegmentExposureInput(2, ThresholdStatus.SAFE, 600),
            SegmentExposureInput(3, ThresholdStatus.CRITICAL, 600),
            SegmentExposureInput(4, ThresholdStatus.SAFE, 600),
            SegmentExposureInput(5, ThresholdStatus.SAFE, 600),
        ]
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        assert result.components["high_risk_segments"] == pytest.approx(40.0, abs=0.01)
        assert result.high_risk_segment_count == 2

    def test_score_is_weighted_sum_clamped(self) -> None:
        inputs = [SegmentExposureInput(1, ThresholdStatus.CRITICAL, 12 * 3600, temperature_c=12.0)]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        expected = (
            WEIGHTS.peak_temperature * 100.0
            + WEIGHTS.duration * 50.0
            + WEIGHTS.persistence * 100.0
            + WEIGHTS.high_risk_segments * 100.0
        )
        # Note: persistence and high_risk_segments weights are 0.0, so only peak and duration count
        assert result.score == pytest.approx(expected, abs=0.01)
        assert 0.0 <= result.score <= 100.0
        # CRITICAL from critical override (12.0 >= 12.0 threshold)
        assert result.level == ThresholdStatus.CRITICAL

    def test_missing_data_produces_uncertainty_signals(self) -> None:
        exp = compute_exposure(
            [
                SegmentExposureInput(1, ThresholdStatus.UNKNOWN, 600),
                SegmentExposureInput(2, ThresholdStatus.UNKNOWN, 600),
            ]
        )
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS)
        assert result.components["peak_temperature"] == 0.0
        assert result.explanation_factors["peak_temperature_missing"] is True
        assert result.explanation_factors["insufficient_observations"] is True
        assert result.explanation_factors["observed_segments"] == 0
        assert result.peak_temperature_c is None

    def test_missing_rule_defaults_to_zero_component(self) -> None:
        exp = ExposureSummary(
            total_segment_count=1,
            observed_segment_count=1,
            exposed_segment_count=1,
            high_risk_segment_count=1,
            time_above_warning_hours=1.0,
            time_above_critical_hours=1.0,
            longest_persistence_hours=1.0,
            peak_temperature_c=10.0,
            average_temperature_c=10.0,
            total_duration_minutes=60.0,
        )
        rules = {
            "duration": {"description": "no max supplied"},
            "exceedance": {"max_minutes": 60},
            "persistence": {"max_minutes": 30},
        }
        result = calculate_risk(exp, profile(exposure_rules=rules), WEIGHTS, BANDS)
        assert result.components["duration"] == 0.0
        assert result.explanation_factors["duration_max_missing"] is True

    def test_zero_weights_do_not_crash(self) -> None:
        exp = compute_exposure(segments([(ThresholdStatus.CRITICAL, 3600)]))
        result = calculate_risk(
            exp,
            profile(),
            RiskWeights(0.0, 0.0, 0.0, 0.0),
            BANDS,
        )
        assert result.score == 0.0
        assert result.level == ThresholdStatus.SAFE

    def test_peak_missing_keeps_other_components(self) -> None:
        exp = ExposureSummary(
            total_segment_count=3,
            observed_segment_count=2,
            exposed_segment_count=2,
            high_risk_segment_count=2,
            time_above_warning_hours=1.0,
            time_above_critical_hours=0.5,
            longest_persistence_hours=0.5,
            peak_temperature_c=None,
            average_temperature_c=None,
            total_duration_minutes=60.0,
        )
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS)
        assert result.components["peak_temperature"] == 0.0
        assert result.components["duration"] > 0.0
        assert result.components["persistence"] > 0.0
        assert result.components["high_risk_segments"] > 0.0