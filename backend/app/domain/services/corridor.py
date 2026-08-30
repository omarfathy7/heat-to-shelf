"""Corridor construction — produce the area of interest for heatmap requests."""

from app.core.config import settings
from app.domain.value_objects.bounding_box import BoundingBox
from app.domain.value_objects.route import RouteData


def route_bbox(route: RouteData, margin_degrees: float | None = None) -> BoundingBox:
    """Envelope of the route polyline, padded by a corridor margin (degrees)."""
    margin = margin_degrees if margin_degrees is not None else settings.corridor_margin_degrees
    lons = [c.longitude for c in route.geometry]
    lats = [c.latitude for c in route.geometry]
    return BoundingBox(
        min_lon=min(lons) - margin,
        min_lat=min(lats) - margin,
        max_lon=max(lons) + margin,
        max_lat=max(lats) + margin,
    )