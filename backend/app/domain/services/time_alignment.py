"""Time alignment — pure: pick sample request times and validate observations."""

from datetime import datetime, timedelta
from typing import Sequence


def sample_request_times(
    departure_utc: datetime,
    last_arrival_utc: datetime,
    arrivals: Sequence[datetime],
    max_samples: int,
) -> list[datetime]:
    """Request times at which heatmaps are fetched.

    Uses per-segment arrival times when under the cap, otherwise evenly-spaced
    samples across the journey window.
    """
    if last_arrival_utc <= departure_utc:
        return [departure_utc]
    uniques: list[datetime] = []
    seen = set()
    for t in arrivals:
        ts = t.timestamp()
        if ts not in seen:
            seen.add(ts)
            uniques.append(t)
    if len(uniques) <= max_samples:
        return uniques
    total = (last_arrival_utc - departure_utc).total_seconds()
    if max_samples <= 1:
        return [departure_utc]
    step = total / (max_samples - 1)
    return [departure_utc + timedelta(seconds=step * i) for i in range(max_samples)]


def nearest_sample(
    moment: datetime,
    sample_times: Sequence[datetime],
    tolerance_minutes: int,
) -> datetime | None:
    """Closest sample time to `moment` within tolerance, else None (unknown)."""
    if not sample_times:
        return None
    best = min(sample_times, key=lambda t: abs((t - moment).total_seconds()))
    if abs((best - moment).total_seconds()) > tolerance_minutes * 60:
        return None
    return best


def within_alignment_tolerance(
    observed_at: datetime,
    segment_arrival: datetime,
    tolerance_minutes: int,
) -> bool:
    return abs((observed_at - segment_arrival).total_seconds()) <= tolerance_minutes * 60