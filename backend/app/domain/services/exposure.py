"""Pure thermal-exposure engine — no I/O, no business rules.

Aggregates per-segment observations (status + duration + temperature) into
journey exposure metrics: time above thresholds, longest consecutive exposure,
peak temperature, and high-risk segment counts. Duration is derived from the
route segmentation; provider exceedance/persistence, when present, is favoured
over the derived estimate (see SegmentExposureInput).
"""

from dataclasses import dataclass
from typing import Sequence

from app.domain.value_objects.thermal_observation import ThresholdStatus

EXPOSED_STATUSES = frozenset(
    {ThresholdStatus.WARNING, ThresholdStatus.HIGH, ThresholdStatus.CRITICAL}
)
HIGH_RISK_STATUSES = frozenset({ThresholdStatus.HIGH, ThresholdStatus.CRITICAL})


@dataclass(frozen=True)
class SegmentExposureInput:
    sequence: int
    status: ThresholdStatus
    duration_seconds: int
    temperature_c: float | None = None
    recorded_exceedance_hours: float | None = None
    recorded_persistence_hours: float | None = None


@dataclass(frozen=True)
class ExposureSummary:
    total_segment_count: int
    observed_segment_count: int
    exposed_segment_count: int
    high_risk_segment_count: int
    time_above_warning_hours: float
    time_above_critical_hours: float
    longest_persistence_hours: float
    peak_temperature_c: float | None
    average_temperature_c: float | None
    total_duration_minutes: float


def is_exposed(status: ThresholdStatus) -> bool:
    return status in EXPOSED_STATUSES


def is_high_risk(status: ThresholdStatus) -> bool:
    return status in HIGH_RISK_STATUSES


def segment_duration_hours(segment: SegmentExposureInput) -> float:
    return max(0.0, segment.duration_seconds / 3600.0)


def segment_exceedance_hours(segment: SegmentExposureInput) -> float | None:
    if segment.recorded_exceedance_hours is not None:
        return segment.recorded_exceedance_hours
    return segment_duration_hours(segment) if is_exposed(segment.status) else 0.0


def segment_persistence_hours(segment: SegmentExposureInput) -> float | None:
    if segment.recorded_persistence_hours is not None:
        return segment.recorded_persistence_hours
    return segment_duration_hours(segment) if is_exposed(segment.status) else 0.0


def compute_exposure(segments: Sequence[SegmentExposureInput]) -> ExposureSummary:
    time_above_warning = 0.0
    time_above_critical = 0.0
    exposed_count = 0
    high_count = 0
    observed_count = 0
    temps: list[float] = []
    max_run_hours = 0.0
    current_run_hours = 0.0

    for segment in segments:
        exposed = is_exposed(segment.status)
        high = is_high_risk(segment.status)
        duration_hours = segment_duration_hours(segment)
        exceedance = segment_exceedance_hours(segment)

        if exposed:
            exposed_count += 1
            time_above_warning += exceedance or duration_hours
            current_run_hours += duration_hours
        else:
            time_above_warning += exceedance or 0.0
            current_run_hours = 0.0
        if high:
            high_count += 1
            time_above_critical += segment_persistence_hours(segment) or duration_hours

        if segment.status != ThresholdStatus.UNKNOWN:
            observed_count += 1
        if segment.temperature_c is not None:
            temps.append(segment.temperature_c)

        max_run_hours = max(max_run_hours, current_run_hours)

    return ExposureSummary(
        total_segment_count=len(segments),
        observed_segment_count=observed_count,
        exposed_segment_count=exposed_count,
        high_risk_segment_count=high_count,
        time_above_warning_hours=round(time_above_warning, 4),
        time_above_critical_hours=round(time_above_critical, 4),
        longest_persistence_hours=round(max_run_hours, 4),
        peak_temperature_c=max(temps) if temps else None,
        average_temperature_c=(sum(temps) / len(temps)) if temps else None,
        total_duration_minutes=round(
            sum(segment_duration_hours(s) for s in segments) * 60.0, 2
        ),
    )