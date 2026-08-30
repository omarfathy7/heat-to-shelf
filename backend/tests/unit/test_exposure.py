import pytest

from app.domain.services.exposure import (
    SegmentExposureInput,
    compute_exposure,
    is_exposed,
    is_high_risk,
)
from app.domain.value_objects.thermal_observation import ThresholdStatus


def seg(
    sequence,
    status,
    duration_seconds,
    temperature_c=None,
    recorded_exceedance_hours=None,
    recorded_persistence_hours=None,
):
    return SegmentExposureInput(
        sequence=sequence,
        status=status,
        duration_seconds=duration_seconds,
        temperature_c=temperature_c,
        recorded_exceedance_hours=recorded_exceedance_hours,
        recorded_persistence_hours=recorded_persistence_hours,
    )


class TestStatusHelpers:
    def test_exposed_statuses(self) -> None:
        assert is_exposed(ThresholdStatus.WARNING) is True
        assert is_exposed(ThresholdStatus.HIGH) is True
        assert is_exposed(ThresholdStatus.CRITICAL) is True
        assert is_exposed(ThresholdStatus.SAFE) is False
        assert is_exposed(ThresholdStatus.UNKNOWN) is False

    def test_high_risk_statuses(self) -> None:
        assert is_high_risk(ThresholdStatus.HIGH) is True
        assert is_high_risk(ThresholdStatus.CRITICAL) is True
        assert is_high_risk(ThresholdStatus.WARNING) is False


class TestComputeExposure:
    def test_aggregates_mixed_journey(self) -> None:
        exp = compute_exposure(
            [
                seg(1, ThresholdStatus.SAFE, 600),
                seg(2, ThresholdStatus.WARNING, 600),
                seg(3, ThresholdStatus.HIGH, 1200),
                seg(4, ThresholdStatus.SAFE, 600),
                seg(5, ThresholdStatus.CRITICAL, 1800),
                seg(6, ThresholdStatus.CRITICAL, 1200),
            ]
        )
        assert exp.total_segment_count == 6
        assert exp.exposed_segment_count == 4
        assert exp.high_risk_segment_count == 3
        assert exp.time_above_warning_hours == pytest.approx((600 + 1200 + 1800 + 1200) / 3600, abs=0.0001)
        assert exp.time_above_critical_hours == pytest.approx((1200 + 1800 + 1200) / 3600, abs=0.0001)
        # longest run is s5+s6 = 3000s
        assert exp.longest_persistence_hours == pytest.approx(3000 / 3600, abs=0.0001)
        assert exp.total_duration_minutes == pytest.approx((600 + 600 + 1200 + 600 + 1800 + 1200) / 60)

    def test_unknown_interrupts_persistence_run(self) -> None:
        exp = compute_exposure(
            [
                seg(1, ThresholdStatus.WARNING, 600),
                seg(2, ThresholdStatus.UNKNOWN, 600),
                seg(3, ThresholdStatus.WARNING, 600),
                seg(4, ThresholdStatus.WARNING, 1200),
            ]
        )
        assert exp.longest_persistence_hours == pytest.approx((600 + 1200) / 3600)
        assert exp.observed_segment_count == 3

    def test_peak_and_average_temperature(self) -> None:
        exp = compute_exposure(
            [
                seg(1, ThresholdStatus.SAFE, 600, temperature_c=3.0),
                seg(2, ThresholdStatus.HIGH, 600, temperature_c=11.0),
                seg(3, ThresholdStatus.UNKNOWN, 600, temperature_c=None),
                seg(4, ThresholdStatus.CRITICAL, 600, temperature_c=25.0),
            ]
        )
        assert exp.peak_temperature_c == 25.0
        assert exp.average_temperature_c == 13.0

    def test_all_unknown_is_empty_journey(self) -> None:
        exp = compute_exposure(
            [
                seg(1, ThresholdStatus.UNKNOWN, 600),
                seg(2, ThresholdStatus.UNKNOWN, 600),
            ]
        )
        assert exp.observed_segment_count == 0
        assert exp.exposed_segment_count == 0
        assert exp.high_risk_segment_count == 0
        assert exp.peak_temperature_c is None
        assert exp.average_temperature_c is None
        assert exp.time_above_warning_hours == 0.0
        assert exp.longest_persistence_hours == 0.0

    def test_recorded_exceedance_overrides_derived(self) -> None:
        exp = compute_exposure(
            [
                seg(1, ThresholdStatus.HIGH, 600, recorded_exceedance_hours=2.0),
                seg(2, ThresholdStatus.SAFE, 600, recorded_exceedance_hours=1.0),
                seg(3, ThresholdStatus.SAFE, 600),
            ]
        )
        assert exp.time_above_warning_hours == 2.0 + 1.0

    def test_empty_inputs(self) -> None:
        exp = compute_exposure([])
        assert exp.total_segment_count == 0
        assert exp.peak_temperature_c is None