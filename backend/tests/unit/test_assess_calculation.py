"""Unit tests for the risk assessment calculation with updated weights and critical override."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.entities.product import ProductProfile
from app.domain.services.cargo_risk import RiskBands, RiskWeights, calculate_risk
from app.domain.services.exposure import SegmentExposureInput, compute_exposure
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


class TestUpdatedWeights:
    def test_normalized_weights_sum_to_one(self) -> None:
        norm = WEIGHTS.normalized()
        assert norm.peak_temperature + norm.duration + norm.persistence + norm.high_risk_segments == pytest.approx(1.0)
        assert norm.persistence == 0.0
        assert norm.high_risk_segments == 0.0
        assert norm.peak_temperature == pytest.approx(0.55)
        assert norm.duration == pytest.approx(0.45)

    def test_zero_persistence_and_high_risk_contribute_nothing(self) -> None:
        exp = compute_exposure(
            [
                SegmentExposureInput(1, ThresholdStatus.CRITICAL, 30 * 60, temperature_c=25.0),
            ]
        )
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=[
            SegmentExposureInput(1, ThresholdStatus.CRITICAL, 30 * 60, temperature_c=25.0),
        ])
        assert result.components["persistence"] > 0.0  # component itself still computed
        assert result.score == pytest.approx(
            0.55 * result.components["peak_temperature"] + 0.45 * result.components["duration"],
            abs=0.01,
        )

    def test_score_83_5_with_correct_duration(self) -> None:
        """The canonical target: score=83.5, level=CRITICAL."""
        # 20 segments, each ~45.6 min = 2736s, total 912 min
        # peak_component = 100 (25C >= 12C critical)
        # duration_component = 912/1440*100 = 63.333
        # score = 0.55*100 + 0.45*63.333 = 55 + 28.5 = 83.5
        seg_dur = 2736  # seconds per segment
        inputs = [
            SegmentExposureInput(sequence=i + 1, status=ThresholdStatus.CRITICAL, duration_seconds=seg_dur, temperature_c=25.0)
            for i in range(20)
        ]
        exp = compute_exposure(inputs)
        assert exp.total_duration_minutes == pytest.approx(912.0, abs=0.1)

        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        assert result.score == pytest.approx(83.5, abs=0.01)
        assert result.level == ThresholdStatus.CRITICAL
        assert result.components["peak_temperature"] == pytest.approx(100.0, abs=0.01)
        assert result.components["duration"] == pytest.approx(63.33, abs=0.1)


class TestCriticalThresholdOverride:
    def test_override_forces_critical_when_peak_exceeds_threshold(self) -> None:
        """Even if the score were below 75, any segment >= critical_threshold => CRITICAL."""
        # 1 segment at 25C (>= 12C critical), very short duration
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.CRITICAL, 60, temperature_c=25.0),
        ]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        # The score might be low due to short duration, but level is CRITICAL due to override
        assert result.level == ThresholdStatus.CRITICAL

    def test_override_does_not_apply_when_no_segment_exceeds_critical(self) -> None:
        """Without the override, normal band logic applies."""
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.WARNING, 7200, temperature_c=9.0),
        ]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        # score is low (short duration), maps to SAFE
        assert result.level == ThresholdStatus.SAFE

    def test_override_with_none_temperatures(self) -> None:
        """Segments with None temperature should not trigger override."""
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.UNKNOWN, 60, temperature_c=None),
        ]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        # No segment >= critical_threshold, so normal band logic
        assert result.level == ThresholdStatus.SAFE

    def test_override_with_mixed_segments(self) -> None:
        """Mix of segments: one critical temperature forces CRITICAL level."""
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.WARNING, 3600, temperature_c=9.0),
            SegmentExposureInput(2, ThresholdStatus.CRITICAL, 60, temperature_c=25.0),
            SegmentExposureInput(3, ThresholdStatus.SAFE, 3600, temperature_c=2.0),
        ]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        assert result.level == ThresholdStatus.CRITICAL

    def test_override_not_triggered_when_below_critical(self) -> None:
        """Temperature above warning but below critical => no override."""
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.HIGH, 36000, temperature_c=10.0),
        ]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS, segment_inputs=inputs)
        # 10.0 < 12.0 critical threshold, so no override; score drives band
        assert result.level in {ThresholdStatus.WARNING, ThresholdStatus.HIGH}

    def test_override_without_segment_inputs_falls_back_to_bands(self) -> None:
        """When segment_inputs is None, no override occurs (backward compat)."""
        inputs = [
            SegmentExposureInput(1, ThresholdStatus.WARNING, 7200, temperature_c=9.0),
        ]
        exp = compute_exposure(inputs)
        result = calculate_risk(exp, profile(), WEIGHTS, BANDS)
        assert result.level == ThresholdStatus.SAFE
