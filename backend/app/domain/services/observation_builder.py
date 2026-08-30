"""Compose matched tiles into normalized observations (pure).

Missing or stale matches become UNKNOWN observations — never silent
substitution of neighboring/stale values.
"""

from datetime import datetime
from typing import Sequence

from app.domain.services.spatial_match import best_tile_for_segment
from app.domain.services.threshold import classify_threshold
from app.domain.services.time_alignment import within_alignment_tolerance
from app.domain.value_objects.thermal import ThermalTile
from app.domain.value_objects.thermal_observation import ThermalObservation, ThresholdStatus

SOURCE = "fortyguard"


def _midpoint(coords: Sequence[tuple[float, float]]) -> tuple[float, float]:
    if not coords:
        return (0.0, 0.0)
    n = len(coords)
    return (
        sum(p[0] for p in coords) / n,
        sum(p[1] for p in coords) / n,
    )


def build_observation(
    *,
    segment_id,
    segment_coords: Sequence[tuple[float, float]],
    arrival_utc: datetime,
    sample_time_utc: datetime | None,
    tiles: Sequence[ThermalTile],
    min_temp_c: float,
    max_temp_c: float,
    warning_threshold_c: float,
    critical_threshold_c: float,
    alignment_tolerance_minutes: int,
    request_hash: str,
) -> ThermalObservation:
    midpoint_lon, midpoint_lat = _midpoint(list(segment_coords))

    if sample_time_utc is None:
        return ThermalObservation(
            segment_id=segment_id,
            latitude=midpoint_lat,
            longitude=midpoint_lon,
            threshold_status=ThresholdStatus.UNKNOWN,
            source=SOURCE,
            source_request_hash="",
            data_quality={"matched": False, "reason": "no_sample_time"},
        )

    tile = best_tile_for_segment(segment_coords, tiles)
    if tile is None:
        return ThermalObservation(
            segment_id=segment_id,
            latitude=midpoint_lat,
            longitude=midpoint_lon,
            threshold_status=ThresholdStatus.UNKNOWN,
            source=SOURCE,
            source_request_hash=request_hash,
            data_quality={"matched": False, "reason": "no_tile_overlap"},
        )

    if not within_alignment_tolerance(tile.observed_at_utc, sample_time_utc, alignment_tolerance_minutes):
        return ThermalObservation(
            segment_id=segment_id,
            latitude=tile.latitude,
            longitude=tile.longitude,
            threshold_status=ThresholdStatus.UNKNOWN,
            source=SOURCE,
            source_request_hash=request_hash,
            data_quality={
                **tile.data_quality,
                "matched": True,
                "matched_tile_id": tile.tile_id,
                "reason": "sample_out_of_tolerance",
            },
        )

    status = classify_threshold(
        tile.temperature_c,
        min_temp_c=min_temp_c,
        max_temp_c=max_temp_c,
        warning_threshold_c=warning_threshold_c,
        critical_threshold_c=critical_threshold_c,
    )
    return ThermalObservation(
        segment_id=segment_id,
        observed_at_utc=tile.observed_at_utc,
        latitude=tile.latitude,
        longitude=tile.longitude,
        temperature_c=tile.temperature_c,
        threshold_status=status,
        source=SOURCE,
        source_request_hash=request_hash,
        data_quality={
            **tile.data_quality,
            "matched": True,
            "matched_tile_id": tile.tile_id,
        },
    )