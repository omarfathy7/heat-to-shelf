from datetime import datetime, timezone

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.route import RouteData
from app.domain.services.route_segmenter import (
    cumulative_lengths,
    estimate_arrivals,
    interpolate_at_distance,
    segment_polyline,
    segment_route,
)


def line_pts(n: int = 5, dx: float = 0.001) -> list[tuple[float, float]]:
    return [(i * dx, 0.0) for i in range(n)]


class TestCumulativeLengths:
    def test_single_segment(self) -> None:
        cum = cumulative_lengths([(0.0, 0.0), (0.01, 0.0)])
        assert cum[0] == 0.0
        assert cum[1] > 0.0

    def test_strictly_increasing(self) -> None:
        cum = cumulative_lengths(line_pts(5))
        assert all(b > a for a, b in zip(cum, cum[1:]))


class TestInterpolation:
    def test_between_points(self) -> None:
        pts = [(0.0, 0.0), (0.01, 0.0)]
        cum = cumulative_lengths(pts)
        mid = interpolate_at_distance(pts, cum, cum[1] / 2)
        assert abs(mid[0] - 0.005) < 1e-6

    def test_endpoints(self) -> None:
        pts = [(0.0, 0.0), (0.01, 1.0)]
        cum = cumulative_lengths(pts)
        assert interpolate_at_distance(pts, cum, 0.0) == (0.0, 0.0)
        assert interpolate_at_distance(pts, cum, cum[-1] + 1) == (0.01, 1.0)


class TestSegmentPolyline:
    def test_two_point_line_into_n(self) -> None:
        segments = segment_polyline([(0.0, 0.0), (0.01, 0.0)], 4)
        assert len(segments) == 4
        for seg in segments:
            assert len(seg) >= 2

    def test_segments_are_ordered_and_continuous(self) -> None:
        segments = segment_polyline(line_pts(20), 5)
        assert len(segments) == 5
        for i in range(1, len(segments)):
            assert segments[i][0] == segments[i - 1][-1]

    def test_first_starts_at_p0_last_ends_at_pn(self) -> None:
        pts = line_pts(20, dx=0.01)
        segments = segment_polyline(pts, 4)
        assert segments[0][0] == pts[0]
        assert segments[-1][-1] == pts[-1]

    def test_invalid_count(self) -> None:
        with pytest.raises(AppError) as exc:
            segment_polyline([(0.0, 0.0), (0.01, 0.0)], 0)
        assert exc.value.code == ErrorCode.ROUTING_PROVIDER_FAILED

    def test_too_few_points(self) -> None:
        with pytest.raises(AppError) as exc:
            segment_polyline([(0.0, 0.0)], 2)
        assert exc.value.code == ErrorCode.ROUTING_PROVIDER_FAILED

    def test_zero_length_polyline(self) -> None:
        with pytest.raises(AppError) as exc:
            segment_polyline([(1.0, 1.0), (1.0, 1.0)], 2)
        assert exc.value.code == ErrorCode.ROUTING_PROVIDER_FAILED


class TestEstimateArrivals:
    def test_arrival_at_last_equals_duration(self) -> None:
        dep = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        arrivals = estimate_arrivals(dep, 3600, [0.5, 1.0])
        assert (arrivals[-1] - dep).total_seconds() == 3600

    def test_arrivals_are_monotonic(self) -> None:
        dep = datetime(2026, 8, 21, 6, tzinfo=timezone.utc)
        arrivals = estimate_arrivals(dep, 900, [0.1, 0.35, 0.7, 1.0])
        assert all(b >= a for a, b in zip(arrivals, arrivals[1:]))


class TestRouteSegmentationIntegration:
    def test_segment_route_full(self) -> None:
        dep = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        route = RouteData(
            provider="test",
            geometry=[
                Coordinate(longitude=-121.8863, latitude=37.3382),
                Coordinate(longitude=-122.4194, latitude=37.7749),
            ],
            distance_meters=79000,
            duration_seconds=3660,
        )
        segments = segment_route(route, dep, 20)
        assert len(segments) == 20
        assert segments[0].sequence == 1
        assert segments[-1].sequence == 20
        assert all(s.estimated_arrival_utc >= dep for s in segments)
        delta = (segments[-1].estimated_arrival_utc - dep).total_seconds()
        assert abs(delta - 3660) < 5
        ends = [s.end_distance_meters for s in segments]
        assert ends == sorted(ends)
        assert ends[-1] == pytest.approx(79000, abs=2561)