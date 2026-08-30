"""Risk Engine v0.1 test suite.

Covers: critical override, missing data, scoring boundaries,
and integration with real cached scenario data from notebooks
07 (single-date separation) and 08 (multi-date validation).
"""

import sys
import json
from pathlib import Path

import pytest

# ── Path setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.risk_engine import (
    RiskEngine, CargoProfile, RiskLevel,
)
from src.schemas import SegmentObservation
from src.loader import load_scenario, build_observations


# ═══ Fixtures ═════════════════════════════════════════

@pytest.fixture
def engine():
    return RiskEngine(CargoProfile(
        name="test-cargo",
        warning_threshold_c=25.0,
        critical_threshold_c=28.0,
        source_name="test",
        source_url="https://example.com",
    ))


def seg(temp, dwell=0.4, sid=0, dist=1.0):
    """Helper: one segment with given temperature."""
    return SegmentObservation(
        segment_id=sid, distance_km=dist, dwell_hours=dwell,
        temperature_c=temp,
    )


# ═══ Critical Override (the hard safety gate) ═══════

class TestCriticalOverride:

    def test_one_segment_at_critical_forces_critical(self, engine):
        """A single 28°C segment must override everything."""
        a = engine.assess([seg(20.0), seg(28.0, sid=1), seg(20.0)])
        assert a.risk_level == RiskLevel.CRITICAL
        assert a.critical_override_triggered is True
        assert 1 in a.critical_segments

    def test_just_below_critical_not_override(self, engine):
        """27.99°C must NOT trigger the override (>= semantics)."""
        a = engine.assess([seg(27.99)])
        assert a.critical_override_triggered is False

    def test_at_exactly_critical_triggers(self, engine):
        """28.0°C exactly MUST trigger (>= not >)."""
        a = engine.assess([seg(28.0)])
        assert a.critical_override_triggered is True

    def test_override_beats_low_weighted_score(self, engine):
        """Even a 'SAFE' weighted score can't mask a critical breach."""
        # 149 safe segments + 1 critical → weighted score stays low
        segments = [seg(15.0, sid=i) for i in range(149)]
        segments.append(seg(31.0, sid=149))
        a = engine.assess(segments)
        assert a.risk_level == RiskLevel.CRITICAL
        assert a.critical_override_triggered is True
        assert 149 in a.critical_segments

    def test_critical_segments_list_is_complete(self, engine):
        segments = [
            seg(28.5, sid=0), seg(29.0, sid=1),
            seg(20.0, sid=2), seg(28.0, sid=3),
        ]
        a = engine.assess(segments)
        assert sorted(a.critical_segments) == [0, 1, 3]


# ═══ Missing data policy ═════════════════════════════

class TestMissingData:

    def test_all_none_returns_insufficient(self, engine):
        a = engine.assess([seg(None), seg(None, sid=1)])
        assert a.data_completeness == "insufficient_data"

    def test_some_none_still_assesses_valid(self, engine):
        a = engine.assess([seg(None), seg(30.0, sid=1)])
        assert a.data_completeness == "complete"

    def test_none_never_counts_as_zero(self, engine):
        """None segments must not inflate or deflate exposure."""
        a = engine.assess([seg(None), seg(30.0, sid=1)])
        # Only the valid segment counts toward exposure
        assert a.segments_above_warning == 1

    def test_none_never_flags_warning_or_critical(self, engine):
        a = engine.assess([seg(None)])
        assert a.critical_override_triggered is False
        assert a.segments_above_warning == 0


# ═══ Scoring & levels ════════════════════════════════

class TestScoring:

    def test_all_safe_is_zero_and_safe(self, engine):
        a = engine.assess([seg(15.0), seg(18.0), seg(20.0)])
        assert a.risk_score == 0.0
        assert a.risk_level == RiskLevel.SAFE

    def test_boundary_exactly_warning_not_above(self, engine):
        """25.0°C exactly → above_warning is strict >, so False."""
        a = engine.assess([seg(25.0)])
        assert a.segments_above_warning == 0
        assert a.severity_component == 0.0

    def test_longest_run_tracks_continuity(self, engine):
        """[hot, hot, cold, hot] → longest run = 2 dwells."""
        segments = [
            seg(30.0, sid=0), seg(30.0, sid=1),
            seg(15.0, sid=2), seg(30.0, sid=3),
        ]
        a = engine.assess(segments)
        assert abs(a.longest_run_hours - 0.8) < 1e-9  # 2 × 0.4

    def test_longest_run_all_hot(self, engine):
        segments = [seg(30.0, sid=i) for i in range(5)]
        a = engine.assess(segments)
        assert abs(a.longest_run_hours - 2.0) < 1e-9  # 5 × 0.4


# ═══ Integration with REAL cached data ═══════════════

CACHE = PROJECT_ROOT / "cache"


def _cached_available():
    return (CACHE / "scenario_2026-08-19_1600.json").exists()


@pytest.mark.skipif(
    not _cached_available(),
    reason="notebook 07/08 cache not present",
)
class TestRealDataIntegration:
    """Validated numbers from notebooks 07 + 08 (placeholder
    thresholds 25/28°C). If these change after the cargo
    citation lands, update EXPECTED below."""

    EXPECTED = {
        ("2026-08-19", "06:00"): (0.0, "SAFE", 0),
        ("2026-08-19", "12:00"): (44.1, "HIGH", 15),
        ("2026-08-19", "16:00"): (83.5, "CRITICAL", 95),
    }

    @pytest.mark.parametrize("hour,expected", [
        ("06:00", EXPECTED[("2026-08-19", "06:00")]),
        ("12:00", EXPECTED[("2026-08-19", "12:00")]),
        ("16:00", EXPECTED[("2026-08-19", "16:00")]),
    ])
    def test_validated_numbers_reproduce(self, engine, hour, expected):
        exp_score, exp_level, exp_segments = expected
        payload = load_scenario(CACHE, "2026-08-19", hour)
        obs = build_observations(payload)
        assert len(obs) == 150

        a = engine.assess(obs)
        assert abs(a.risk_score - exp_score) <= 0.1
        assert a.risk_level.value == exp_level
        assert a.segments_above_warning == exp_segments

    def test_override_fires_on_real_1600(self, engine):
        payload = load_scenario(CACHE, "2026-08-19", "16:00")
        a = engine.assess(build_observations(payload))
        assert a.critical_override_triggered is True

    @pytest.mark.parametrize("date", [
        "2026-08-19", "2026-08-15", "2026-08-10",
    ])
    def test_0600_safe_on_all_validated_dates(self, engine, date):
        """From multi-date validation: 06:00 is SAFE everywhere."""
        f = CACHE / f"scenario_{date}_0600.json"
        if not f.exists():
            pytest.skip(f"cache for {date} not present")
        payload = load_scenario(CACHE, date, "06:00")
        a = engine.assess(build_observations(payload))
        assert a.risk_level == RiskLevel.SAFE