"""Spatial matching: route segments vs. heatmap tile polygons (pure, shapely)."""

from typing import Sequence

from shapely.geometry import LineString, Polygon

from app.domain.value_objects.thermal import ThermalTile

MIN_INTERSECTION_RATIO = 0.0


def intersects_length(
    line_coords: Sequence[tuple[float, float]],
    polygon_coords: Sequence[tuple[float, float]],
) -> float:
    line = LineString(line_coords)
    poly = Polygon(polygon_coords)
    if line.is_empty or poly.is_empty or not line.intersects(poly):
        return 0.0
    inter = line.intersection(poly)
    if inter.is_empty:
        return 0.0
    if inter.geom_type == "MultiLineString":
        return sum(g.length for g in inter.geoms)
    return inter.length


def best_tile_for_segment(
    line_coords: Sequence[tuple[float, float]],
    tiles: Sequence[ThermalTile],
) -> ThermalTile | None:
    """Pick the tile with the greatest line/polygon overlap for a segment.

    Returns None (missing) when no tile overlaps — never silently substitutes.
    """
    best: ThermalTile | None = None
    best_length = MIN_INTERSECTION_RATIO
    for tile in tiles:
        length = intersects_length(line_coords, tile.polygon)
        if length > best_length:
            best = tile
            best_length = length
    return best


def segment_order_from_origin(segments: Sequence) -> list:
    """Segments are already ordered by sequence (origin -> destination)."""
    return list(segments)