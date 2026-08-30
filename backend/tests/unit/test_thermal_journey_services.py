from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from shapely.geometry import Polygon

from app.domain.services.observation_builder import build_observation
from app.domain.services.spatial_match import best_tile_for_segment, intersects_length
from app.domain.services.threshold import classify_threshold
from app.domain.services.time_alignment import (
    nearest_sample,
    sample_request_times,
    within_alignment_tolerance,
)
from app.domain.value_objects.thermal import ThermalTile
from app.domain.value_objects.thermal_observation import ThresholdStatus

UTC = timezone.utc


def tile(observed_at: datetime, temperature: float, polygon_xy, tile_id: str = "t1") -> ThermalTile:
    lons = [p[0] for p in polygon_xy]
    lats = [p[1] for p in polygon_xy]
    return ThermalTile(
        tile_id=tile_id,
        longitude=sum(lons) / len(lons),
        latitude=sum(lats) / len(lats),
        temperature_c=temperature,
        observed_at_utc=observed_at,
        polygon=polygon_xy,
        data_quality={"quality": "good", "stale": False, "stale_minutes": 0},
    )


def square(min_lon, min_lat, max_lon, max_lat):
    return [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
        (min_lon, min_lat),
    ]


class TestClassifyThreshold:
    def test_band_mapping(self) -> None:
        # profile: safe [0,4], warning (4,8], high (8,12], critical >12, cold excursion <0
        assert classify_threshold(2.0, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.SAFE
        assert classify_threshold(4.0, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.SAFE
        assert classify_threshold(4.5, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.WARNING
        assert classify_threshold(8.0, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.WARNING
        assert classify_threshold(8.5, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.HIGH
        assert classify_threshold(12.0, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.HIGH
        assert classify_threshold(12.5, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.CRITICAL
        assert classify_threshold(-0.5, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.WARNING

    def test_missing_temperature_unknown(self) -> None:
        assert classify_threshold(None, min_temp_c=0, max_temp_c=4, warning_threshold_c=8, critical_threshold_c=12) == ThresholdStatus.UNKNOWN


class TestSampleRequestTimes:
    def test_under_cap_uses_arrivals(self) -> None:
        dep = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        arrivals = [dep + timedelta(minutes=5), dep + timedelta(minutes=10), dep + timedelta(minutes=15)]
        times = sample_request_times(dep, arrivals[-1], arrivals, max_samples=20)
        assert times == arrivals

    def test_over_cap_evenly_spaced(self) -> None:
        dep = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        arrivals = [dep + timedelta(minutes=i * 21) for i in range(10)]
        times = sample_request_times(dep, arrivals[-1], arrivals, max_samples=3)
        assert len(times) == 3
        assert times[0] == dep
        assert times[-1] == arrivals[-1]
        assert (times[1] - times[0]) == (times[2] - times[1])

    def test_duplicate_and_flat_window(self) -> None:
        dep = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        assert sample_request_times(dep, dep, [dep, dep], max_samples=5) == [dep]


class TestNearestSample:
    def test_within_tolerance(self) -> None:
        dep = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        samples = [dep, dep + timedelta(minutes=30), dep + timedelta(minutes=60)]
        best = nearest_sample(dep + timedelta(minutes=28), samples, tolerance_minutes=60)
        assert best == dep + timedelta(minutes=30)

    def test_outside_tolerance(self) -> None:
        dep = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        samples = [dep + timedelta(hours=6)]
        assert nearest_sample(dep, samples, tolerance_minutes=60) is None

    def test_empty_returns_none(self) -> None:
        assert nearest_sample(datetime(2026, 8, 21, 12, 0, tzinfo=UTC), [], tolerance_minutes=60) is None


class TestAlignment:
    def test_within_alignment_tolerance(self) -> None:
        a = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        assert within_alignment_tolerance(a, a + timedelta(minutes=59), 60) is True
        assert within_alignment_tolerance(a, a + timedelta(minutes=61), 60) is False


class TestSpatialMatch:
    def test_intersects_length_inside(self) -> None:
        seg = [(0.0, 0.0), (10.0, 10.0)]
        poly = square(-1.0, -1.0, 11.0, 11.0)
        length = intersects_length(seg, poly)
        assert length > 0
        # OSGeo length approximation; just assert a positive overlap
        diag = (10.0 ** 2 + 10.0 ** 2) ** 0.5
        assert length < diag * 1.01

    def test_no_intersection_zero(self) -> None:
        seg = [(50.0, 50.0), (51.0, 51.0)]
        poly = square(-1.0, -1.0, 1.0, 1.0)
        assert intersects_length(seg, poly) == 0.0

    def test_best_tile_picks_widest_overlap(self) -> None:
        seg = [(0.0, 0.0), (4.0, 0.0)]
        small = tile(datetime(2026, 8, 21, 12, 0, tzinfo=UTC), 10.0, square(0.0, -1.0, 2.0, 1.0), tile_id="small")
        big = tile(datetime(2026, 8, 21, 12, 0, tzinfo=UTC), 25.0, square(-1.0, -1.0, 5.0, 1.0), tile_id="big")
        best = best_tile_for_segment(seg, [small, big])
        assert best is not None
        assert best.tile_id == "big"

    def test_best_tile_none_when_no_overlap(self) -> None:
        seg = [(50.0, 50.0), (51.0, 51.0)]
        far = tile(datetime(2026, 8, 21, 12, 0, tzinfo=UTC), 10.0, square(-1.0, -1.0, 1.0, 1.0))
        assert best_tile_for_segment(seg, [far]) is None


class TestBuildObservation:
    MIN, MAX, WARN, CRIT = 0.0, 4.0, 8.0, 12.0

    def _obs(self, **overrides):
        kwargs = dict(
            segment_id=str(uuid4()),
            segment_coords=[(0.0, 0.0), (4.0, 4.0)],
            arrival_utc=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            sample_time_utc=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            tiles=[],
            min_temp_c=self.MIN,
            max_temp_c=self.MAX,
            warning_threshold_c=self.WARN,
            critical_threshold_c=self.CRIT,
            alignment_tolerance_minutes=60,
            request_hash="h",
        )
        kwargs.update(overrides)
        return build_observation(**kwargs)

    def test_matched_valid_classifies(self) -> None:
        t = tile(
            datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            25.0,
            square(-1.0, -1.0, 5.0, 5.0),
        )
        obs = self._obs(tiles=[t])
        assert obs.threshold_status == ThresholdStatus.CRITICAL
        assert obs.temperature_c == 25.0
        assert obs.data_quality["matched"] is True
        assert obs.observed_at_utc == t.observed_at_utc

    def test_classified_safe(self) -> None:
        t = tile(
            datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            3.0,
            square(-1.0, -1.0, 5.0, 5.0),
        )
        obs = self._obs(tiles=[t])
        assert obs.threshold_status == ThresholdStatus.SAFE
        assert obs.temperature_c == 3.0

    def test_no_tile_overlap_unknown(self) -> None:
        far = tile(datetime(2026, 8, 21, 12, 0, tzinfo=UTC), 10.0, square(50.0, 50.0, 51.0, 51.0))
        obs = self._obs(tiles=[far])
        assert obs.threshold_status == ThresholdStatus.UNKNOWN
        assert obs.temperature_c is None
        assert obs.data_quality["reason"] == "no_tile_overlap"
        assert obs.data_quality["matched"] is False
        # location falls back to segment midpoint, not the far tile
        assert obs.latitude == 2.0 and abs(obs.longitude - 2.0) < 1e-9

    def test_stale_sample_unknown(self) -> None:
        now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        stale_tile = tile(now - timedelta(hours=5), 25.0, square(-1.0, -1.0, 5.0, 5.0))
        obs = self._obs(tiles=[stale_tile])
        assert obs.threshold_status == ThresholdStatus.UNKNOWN
        assert obs.temperature_c is None
        assert obs.data_quality["reason"] == "sample_out_of_tolerance"

    def test_no_sample_time_unknown(self) -> None:
        obs = self._obs(sample_time_utc=None)
        assert obs.threshold_status == ThresholdStatus.UNKNOWN
        assert obs.temperature_c is None
        assert obs.data_quality["reason"] == "no_sample_time"


def test_tile_polygon_shapes_closed() -> None:
    ring = square(0.0, 0.0, 1.0, 1.0)
    assert len(ring) == 5
    assert ring[0] == ring[-1]
    assert Polygon(ring).is_valid is True