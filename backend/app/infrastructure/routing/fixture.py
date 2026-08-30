import json
from pathlib import Path

from app.core.errors import AppError, ErrorCode
from app.domain.interfaces.providers import RoutingProvider
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.route import RouteData

DEFAULT_FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "routes" / "san_jose_to_san_francisco.json"


class FixtureRoutingProvider(RoutingProvider):
    """Offline routing source for local development and tests only.

    Never used for live analysis; results must be clearly labeled as fixture data.
    """

    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or DEFAULT_FIXTURE

    async def build_route(self, origin: Coordinate, destination: Coordinate) -> RouteData:
        try:
            payload = json.loads(self.fixture_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError(
                ErrorCode.ROUTING_PROVIDER_FAILED,
                f"fixture route unavailable: {self.fixture_path.name}",
            ) from exc

        coords = [
            Coordinate(longitude=p["longitude"], latitude=p["latitude"])
            for p in payload["geometry"]
        ]
        route = RouteData(
            provider=payload.get("provider", "fixture"),
            provider_route_id=payload.get("provider_route_id"),
            geometry=coords,
            distance_meters=payload["distance_meters"],
            duration_seconds=payload["duration_seconds"],
            raw_response_ref=payload.get("raw_response_ref"),
            metadata={"fixture": True, "source_path": str(self.fixture_path)},
        )
        return route