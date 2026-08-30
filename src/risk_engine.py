"""
Risk Engine v0.1 — Heat-to-Shelf
Methodology: Severity + Duration only (per plan §10 revision).
Persistence removed from weighted score; kept as contextual signal.
Critical Override: any segment >= critical_threshold → risk level
force-set to CRITICAL regardless of weighted score.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

# ── Single source of truth — no duplicate definitions ──
# SegmentObservation lives ONLY in schemas.py now.
try:
    from src.schemas import SegmentObservation
except ImportError:
    # Direct-execution fallback (python src/risk_engine.py)
    from schemas import SegmentObservation


class RiskLevel(str, Enum):
    """Single source of truth — used by engine, API, UI, reports."""
    SAFE = "SAFE"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class CargoProfile:
    """Thermal requirements for the shipment. Must come from
    credible external sources — never invented."""
    name: str
    warning_threshold_c: float
    critical_threshold_c: float
    source_name: str
    source_url: str


@dataclass
class RiskAssessment:
    """Complete risk result — reproducible from inputs."""
    risk_score: float
    risk_level: RiskLevel
    severity_component: float
    duration_component: float
    critical_override_triggered: bool
    critical_segments: List[int] = field(default_factory=list)
    exposure_hours: float = 0.0
    longest_run_hours: float = 0.0
    segments_above_warning: int = 0
    methodology_version: str = "v0.1"
    data_completeness: str = "complete"  # or "insufficient_data"


# ── Normalization helpers ──────────────────────────────────

def normalize_severity(temp_c: float, warning_c: float,
                       critical_c: float) -> float:
    """Map temperature to 0-1 severity scale.
    Below warning → 0. At critical → 1. Linear between."""
    if temp_c <= warning_c:
        return 0.0
    if temp_c >= critical_c:
        return 1.0
    return (temp_c - warning_c) / (critical_c - warning_c)


def normalize_duration(exposure_h: float, total_trip_h: float) -> float:
    """Fraction of trip time spent above warning threshold. 0-1."""
    if total_trip_h <= 0:
        return 0.0
    return min(exposure_h / total_trip_h, 1.0)


# ── Core engine ────────────────────────────────────────────

class RiskEngine:
    """v0.1: Risk = 0.55 * Severity + 0.45 * Duration
    Critical Override: any segment >= critical → CRITICAL.

    NOTE: All weights and score bands are PROVISIONAL (v0.1 MVP
    policy, not scientific claims). Sensitivity check performed:
    scenario RANKING is stable across 55/45 vs 40/60 weightings
    (06:00 best, 16:00 worst in both); the Critical Override is
    weight-independent entirely (absolute threshold, not score).
    Only the mid-scenario band shifts WARNING<->HIGH between
    weightings — documented as provisional for this reason.
    See 'Evaluation' section in README.
    """

    WEIGHT_SEVERITY = 0.55   # PROVISIONAL v0.1
    WEIGHT_DURATION = 0.45   # PROVISIONAL v0.1

    # PROVISIONAL v0.1 bands
    SCORE_SAFE = 0.15
    SCORE_WARNING = 0.40
    SCORE_HIGH = 0.70

    def __init__(self, cargo: CargoProfile):
        self.cargo = cargo

    def assess(self, segments: List[SegmentObservation]) -> RiskAssessment:
        # Flag segments against thresholds
        for seg in segments:
            if seg.temperature_c is None:
                continue
            seg.above_warning = seg.temperature_c > self.cargo.warning_threshold_c
            seg.above_critical = seg.temperature_c >= self.cargo.critical_threshold_c

        valid = [s for s in segments if s.temperature_c is not None]
        if not valid:
            return RiskAssessment(
                risk_score=0.0, risk_level=RiskLevel.SAFE,
                severity_component=0.0, duration_component=0.0,
                critical_override_triggered=False,
                data_completeness="insufficient_data",
            )

        total_trip_h = sum(s.dwell_hours for s in segments)

        # ── Severity: peak temperature normalized ──
        peak_temp = max(s.temperature_c for s in valid)
        severity = normalize_severity(
            peak_temp,
            self.cargo.warning_threshold_c,
            self.cargo.critical_threshold_c,
        )

        # ── Duration: exposure fraction (piecewise-constant) ──
        exposure_h = sum(
            s.dwell_hours for s in valid if s.above_warning
        )
        duration = normalize_duration(exposure_h, total_trip_h)

        # ── Longest continuous run (contextual, not in score) ──
        longest, current = 0.0, 0.0
        for s in segments:
            if s.above_warning:
                current += s.dwell_hours
                longest = max(longest, current)
            else:
                current = 0.0

        # ── Weighted score ──
        score = (
            self.WEIGHT_SEVERITY * severity
            + self.WEIGHT_DURATION * duration
        )

        # ── Critical Override (hard safety gate) ──
        critical_segments = [s.segment_id for s in valid if s.above_critical]
        override = len(critical_segments) > 0

        if override:
            level = RiskLevel.CRITICAL
        elif score < self.SCORE_SAFE:
            level = RiskLevel.SAFE
        elif score < self.SCORE_WARNING:
            level = RiskLevel.WARNING
        else:
            level = RiskLevel.HIGH

        return RiskAssessment(
            risk_score=round(score * 100, 1),  # display 0-100
            risk_level=level,
            severity_component=round(severity, 3),
            duration_component=round(duration, 3),
            critical_override_triggered=override,
            critical_segments=critical_segments,
            exposure_hours=round(exposure_h, 3),
            longest_run_hours=round(longest, 3),
            segments_above_warning=sum(1 for s in valid if s.above_warning),
        )