"""PostGIS geometry helpers: domain coords <-> WKT elements."""

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape


def point_wkt(longitude: float, latitude: float) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def line_wkt(coords: list[tuple[float, float]]) -> WKTElement:
    body = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    return WKTElement(f"LINESTRING({body})", srid=4326)


def coords_from(element) -> list[tuple[float, float]]:
    """Ordered (longitude, latitude) tuples read from a PostGIS geometry element."""
    if element is None:
        return []
    return [tuple(c) for c in to_shape(element).coords]