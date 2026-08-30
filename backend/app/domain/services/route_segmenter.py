"""Pure route segmentation and arrival-time estimation.

No I/O; operates on coordinate lists. Distances approximate via haversine,
fractions are then scaled to the provider-reported route totals so arrival at
the last segment equals the route duration.
"""

import math
from datetime import datetime, timedelta
from typing import Sequence

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.route import RouteData, RouteSegment

EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def cumulative_lengths(points: Sequence[tuple[float, float]]) -> list[float]:
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + _haversine_m(a, b))
    return cum


def interpolate_at_distance(
    points: Sequence[tuple[float, float]],
    cum: Sequence[float],
    target: float,
) -> tuple[float, float]:
    if target <= cum[0]:
        return points[0]
    if target >= cum[-1]:
        return points[-1]
    for i in range(len(cum) - 1):
        if cum[i] <= target <= cum[i + 1]:
            span = cum[i + 1] - cum[i]
            t = 0.0 if span == 0 else (target - cum[i]) / span
            a, b = points[i], points[i + 1]
            return (
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
            )
    return points[-1]


def segment_polyline(
    points: Sequence[tuple[float, float]],
    segment_count: int,
) -> list[list[tuple[float, float]]]:
    """Split a polyline into `segment_count` consecutive, equal-length pieces."""
    if segment_count < 1:
        raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "segment count must be >= 1")
    if len(points) < 2:
        raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "polyline must have at least two points")

    cum = cumulative_lengths(points)
    total = cum[-1]
    if total <= 0:
        raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "polyline has zero length")

    breaks = [interpolate_at_distance(points, cum, total * k / segment_count) for k in range(segment_count + 1)]

    segments: list[list[tuple[float, float]]] = []
    for k in range(segment_count):
        lo, hi = total * k / segment_count, total * (k + 1) / segment_count
        seg = [breaks[k]]
        for i in range(1, len(points) - 1):
            if cum[i] >= lo and cum[i] <= hi:
                seg.append(points[i])
        seg.append(breaks[k + 1])
        segments.append(seg)
    return segments


def estimate_arrivals(
    departure_utc: datetime,
    duration_seconds: int,
    end_fractions: Sequence[float],
) -> list[datetime]:
    """Arrival at each segment end = departure + fraction of total duration."""
    return [
        departure_utc + timedelta(seconds=round(f * duration_seconds))
        for f in end_fractions
    ]


def segment_route(
    route: RouteData,
    departure_utc: datetime,
    segment_count: int,
) -> list[RouteSegment]:
    """Build ordered RouteSegments from a validated RouteData."""
    points = [(c.longitude, c.latitude) for c in route.geometry]
    raw_segments = segment_polyline(points, segment_count)

    cum = cumulative_lengths(points)
    total_geo = cum[-1]
    end_fractions = [sum(cumulative_lengths(s)) / total_geo for s in raw_segments]
    # accumulate fractions over whole route so arrival at the end == route duration
    accumulated: list[float] = []
    acc = 0.0
    for f in end_fractions:
        acc += f
        accumulated.append(min(acc, 1.0))
    arrivals = estimate_arrivals(departure_utc, route.duration_seconds, accumulated)

    segments: list[RouteSegment] = []
    start_dist = 0.0
    prev_arrival = departure_utc
    for i, raw in enumerate(raw_segments):
        seg_dist = route.distance_meters * end_fractions[i]
        end_dist = start_dist + seg_dist
        geometry = [Coordinate(longitude=p[0], latitude=p[1]) for p in raw]
        segments.append(
            RouteSegment(
                sequence=i + 1,
                geometry=geometry,
                start_distance_meters=round(start_dist, 2),
                end_distance_meters=round(end_dist, 2),
                estimated_arrival_utc=arrivals[i],
                duration_seconds=max(0, int((arrivals[i] - prev_arrival).total_seconds())),
            )
        )
        start_dist = end_dist
        prev_arrival = arrivals[i]
    return segments