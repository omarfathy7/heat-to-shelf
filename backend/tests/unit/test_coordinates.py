import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.coordinates import Coordinate


class TestCoordinateValidation:
    def test_valid(self) -> None:
        c = Coordinate(longitude=-121.8863, latitude=37.3382)
        assert c.latitude == 37.3382
        assert c.longitude == -121.8863

    def test_latitude_out_of_range(self) -> None:
        with pytest.raises(AppError) as exc:
            Coordinate(longitude=0.0, latitude=91.0)
        assert exc.value.code == ErrorCode.INVALID_COORDINATES

    def test_longitude_out_of_range(self) -> None:
        with pytest.raises(AppError) as exc:
            Coordinate(longitude=181.0, latitude=0.0)
        assert exc.value.code == ErrorCode.INVALID_COORDINATES

    def test_boundary_values_accepted(self) -> None:
        Coordinate(longitude=-180.0, latitude=-90.0)
        Coordinate(longitude=180.0, latitude=90.0)

    @pytest.mark.parametrize("lon,lat", [(0.0, 0.0), (-122.4194, 37.7749)])
    def test_as_tuple_order_is_lon_lat(self, lon: float, lat: float) -> None:
        # Explicit contract: (longitude, latitude) — never reversed.
        assert Coordinate(longitude=lon, latitude=lat).as_tuple() == (lon, lat)

    def test_as_geojson(self) -> None:
        c = Coordinate(longitude=-121.8863, latitude=37.3382)
        assert c.as_geojson() == {"type": "Point", "coordinates": [-121.8863, 37.3382]}