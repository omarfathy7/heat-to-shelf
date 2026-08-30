from datetime import datetime, timezone
from uuid import uuid4

from app.domain.services.recommendation import build_recommendation
from app.domain.services.scenario_comparison import (
    ScenarioOutcome,
    exposure_reduction_percent,
    is_level_improved,
    rank_scenarios,
)
from app.domain.value_objects.thermal_observation import ThresholdStatus

UTC = timezone.utc


def outcome(
    departure: datetime,
    score: float,
    level: ThresholdStatus = ThresholdStatus.SAFE,
    components: dict | None = None,
) -> ScenarioOutcome:
    return ScenarioOutcome(
        id=uuid4(),
        departure_time_utc=departure,
        score=score,
        level=level,
        components=components or {"pk": 0.0},
        peak_temperature_c=None,
        time_above_threshold_hours=0.0,
        longest_persistence_hours=0.0,
        high_risk_segment_count=0,
    )


def full_components(peak=10.0, duration=5.0, persistence=5.0, high=10.0) -> dict:
    return {
        "peak_temperature": peak,
        "duration": duration,
        "persistence": persistence,
        "high_risk_segments": high,
    }


class TestRankScenarios:
    def test_sorts_by_score_ascending(self) -> None:
        morning = outcome(datetime(2026, 8, 21, 6, tzinfo=UTC), score=30.0)
        noon = outcome(datetime(2026, 8, 21, 12, tzinfo=UTC), score=20.0)
        evening = outcome(datetime(2026, 8, 21, 19, tzinfo=UTC), score=40.0)
        ranked = rank_scenarios([morning, noon, evening])
        assert [o.departure_time_utc for o in ranked] == [
            noon.departure_time_utc,
            morning.departure_time_utc,
            evening.departure_time_utc,
        ]
        assert [o.rank for o in ranked] == [1, 2, 3]

    def test_tie_breaks_earlier_departure(self) -> None:
        morning = outcome(datetime(2026, 8, 21, 6, tzinfo=UTC), score=20.0)
        noon = outcome(datetime(2026, 8, 21, 12, tzinfo=UTC), score=20.0)
        ranked = rank_scenarios([noon, morning])
        assert ranked[0].departure_time_utc == morning.departure_time_utc
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2

    def test_does_not_mutate_input(self) -> None:
        morning = outcome(datetime(2026, 8, 21, 6, tzinfo=UTC), score=20.0)
        noon = outcome(datetime(2026, 8, 21, 12, tzinfo=UTC), score=10.0)
        inputs = [morning, noon]
        ranked = rank_scenarios(inputs)
        assert all(o.rank is None for o in inputs)
        assert [o.rank for o in ranked] == [1, 2]


class TestExposureReduction:
    def test_basic_reduction(self) -> None:
        assert exposure_reduction_percent(100.0, 60.0) == 40.0
        assert exposure_reduction_percent(50.0, 20.0) == 60.0

    def test_no_change(self) -> None:
        assert exposure_reduction_percent(80.0, 80.0) == 0.0

    def test_zero_original_handled(self) -> None:
        assert exposure_reduction_percent(0.0, 0.0) == 0.0
        assert exposure_reduction_percent(0.0, 15.0) == 0.0


class TestLevelImprovement:
    def test_severity_ordering(self) -> None:
        assert is_level_improved(ThresholdStatus.CRITICAL, ThresholdStatus.WARNING) is True
        assert is_level_improved(ThresholdStatus.CRITICAL, ThresholdStatus.CRITICAL) is False
        assert is_level_improved(ThresholdStatus.SAFE, ThresholdStatus.HIGH) is False


class TestBuildRecommendation:
    def test_lower_score_emits_reason_codes(self) -> None:
        original = outcome(
            datetime(2026, 8, 21, 12, tzinfo=UTC),
            score=72.0,
            level=ThresholdStatus.HIGH,
            components=full_components(peak=90.0, duration=80.0, persistence=80.0, high=90.0),
        )
        recommended = outcome(
            datetime(2026, 8, 21, 6, tzinfo=UTC),
            score=45.0,
            level=ThresholdStatus.WARNING,
            components=full_components(peak=30.0, duration=20.0, persistence=20.0, high=10.0),
        )
        draft = build_recommendation(original=original, recommended=recommended)
        assert "lower_risk_score" in draft.reason_codes
        assert "lower_peak_temperature" in draft.reason_codes
        assert "less_time_above_threshold" in draft.reason_codes
        assert "lower_persistence" in draft.reason_codes
        assert "fewer_high_risk_segments" in draft.reason_codes
        assert draft.recommended_scenario_id == recommended.id
        assert draft.original_score == 72.0
        assert draft.recommended_score == 45.0
        assert draft.exposure_reduction_percent == round((72 - 45) / 72 * 100, 4)
        assert draft.recommended is True

    def test_equal_scores_produce_no_reason_codes(self) -> None:
        original = outcome(
            datetime(2026, 8, 21, 12, tzinfo=UTC),
            score=40.0,
            components=full_components(peak=40.0),
        )
        recommended = outcome(
            datetime(2026, 8, 21, 6, tzinfo=UTC),
            score=40.0,
            components=full_components(peak=40.0),
        )
        draft = build_recommendation(original=original, recommended=recommended)
        assert draft.reason_codes == []
        assert draft.exposure_reduction_percent == 0.0
        assert draft.recommended is False

    def test_level_change_recorded_in_factors(self) -> None:
        original = outcome(
            datetime(2026, 8, 21, 12, tzinfo=UTC),
            score=80.0,
            level=ThresholdStatus.CRITICAL,
            components=full_components(peak=80.0),
        )
        recommended = outcome(
            datetime(2026, 8, 21, 6, tzinfo=UTC),
            score=20.0,
            level=ThresholdStatus.SAFE,
            components=full_components(peak=20.0),
        )
        draft = build_recommendation(original=original, recommended=recommended)
        assert draft.explanation_factors["level_improved"] is True
        assert draft.explanation_factors["original_level"] == "critical"
        assert draft.explanation_factors["recommended_level"] == "safe"
        assert draft.original_level == ThresholdStatus.CRITICAL
        assert draft.recommended_level == ThresholdStatus.SAFE