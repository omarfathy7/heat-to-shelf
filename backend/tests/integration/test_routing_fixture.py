from datetime import datetime, timezone

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.coordinates import Coordinate
from app.domain.services.route_segmenter import segment_route
from app.infrastructure.routing.fixture import FixtureRoutingProvider


@pytest.fixture()
async def fixture_route():
    provider = FixtureRoutingProvider()
    origin = Coordinate(longitude=-121.8863, latitude=37.3382)
    destination = Coordinate(longitude=-122.4194, latitude=37.7749)
    route = await provider.build_route(origin, destination)
    return route


@pytest.mark.anyio
class TestFixtureRoutingProvider:
    async def test_build_valid_route(self, fixture_route) -> None:
        assert fixture_route.provider == "fixture"
        assert fixture_route.distance_meters > 0
        assert fixture_route.duration_seconds > 0
        assert len(fixture_route.geometry) >= 2

    async def test_geometry_order_and_bounds(self, fixture_route) -> None:
        # Coords must remain (longitude, latitude) and stay in WGS84 ranges.
        for c in fixture_route.geometry:
            assert -180 <= c.longitude <= 180
            assert -90 <= c.latitude <= 90
        first = fixture_route.geometry[0]
        last = fixture_route.geometry[-1]
        assert (first.longitude, first.latitude) == (-121.8863, 37.3382)
        assert (last.longitude, last.latitude) == (-122.4194, 37.7749)

    async def test_segments_from_fixture(self, fixture_route) -> None:
        dep = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        segments = segment_route(fixture_route, dep, 20)
        assert len(segments) == 20
        assert segments[0].geometry[0] == fixture_route.geometry[0]
        assert segments[-1].geometry[-1] == fixture_route.geometry[-1]


class TestMissingFixtureFile:
    @pytest.mark.anyio
    async def test_missing_fixture_raises_route_error(self) -> None:
        from pathlib import Path

        provider = FixtureRoutingProvider(fixture_path=Path("/nonexistent/route.json"))
        with pytest.raises(AppError) as exc:
            await provider.build_route(
                Coordinate(longitude=-121.8863, latitude=37.3382),
                Coordinate(longitude=-122.4194, latitude=37.7749),
            )
        assert exc.value.code == ErrorCode.ROUTING_PROVIDER_FAILED