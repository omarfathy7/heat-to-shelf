"""Single source of truth for all persisted data shapes.
Any file that reads OR writes scenario data imports from here."""

from dataclasses import dataclass
from typing import List, Optional

# ── Summary CSV columns (written by notebook, read by app) ──
SUMMARY_COLUMNS = [
    "hour",
    "peak_temp_c",
    "mean_temp_c",
    "segments_above_threshold",
    "exposure_minutes",
    "longest_run_minutes",
    "match_rate",
]

# ── Per-segment payload keys (written by notebook, read by loader) ──
SEGMENT_KEYS = ["segment_id", "distance_km", "dwell_hours", "temperature_c"]

# ── Scenario payload envelope ──
PAYLOAD_KEYS = [
    "study_date", "hour", "threshold_c",
    "route",           # {distance_km, duration_hours, n_samples}
    "corridor_m", "granularity_m", "match_rate",
    "segments",        # List[dict] with SEGMENT_KEYS
]


@dataclass
class SegmentObservation:
    """One route segment with its thermal observation.
    Matches SEGMENT_KEYS — loader constructs these from cache."""
    segment_id: int
    distance_km: float
    dwell_hours: float          # piecewise-constant model
    temperature_c: Optional[float]
    above_warning: bool = False
    above_critical: bool = False