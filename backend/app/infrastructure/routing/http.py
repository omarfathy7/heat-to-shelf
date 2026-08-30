import logging

import httpx

from app.core.errors import AppError, ErrorCode
from app.domain.interfaces.providers import RoutingProvider
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.route import RouteData
from app.core.config import settings

logger = logging.getLogger(__name__)


class HttpRoutingProvider(RoutingProvider):
    """HTTP routing provider behind the RoutingProvider interface.

    The real endpoint/contract is provided by the validated provider; credentials
    must live in server-side configuration only. If none are configured, fails
    cleanly instead of guessing.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (base_url or settings.routing_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.routing_api_key
        self.timeout = timeout

    async def build_route(self, origin: Coordinate, destination: Coordinate) -> RouteData:
        if not self.base_url or not self.api_key:
            raise AppError(
                ErrorCode.ROUTING_PROVIDER_FAILED,
                "routing provider not configured",
                status_code=503,
            )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "origin": {"latitude": origin.latitude, "longitude": origin.longitude},
            "destination": {"latitude": destination.latitude, "longitude": destination.longitude},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/route", json=payload, headers=headers)
                resp.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("routing_timeout")
            raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "routing provider timed out", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("routing_http_error", extra={"status": exc.response.status_code})
            raise AppError(
                ErrorCode.ROUTING_PROVIDER_FAILED,
                f"routing provider returned {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("routing_connection_error")
            raise AppError(ErrorCode.ROUTING_PROVIDER_FAILED, "routing provider unreachable", status_code=503) from exc

        data = resp.json()
        coords = [Coordinate(longitude=p["longitude"], latitude=p["latitude"]) for p in data["geometry"]]
        return RouteData(
            provider=data.get("provider", "http"),
            provider_route_id=data.get("provider_route_id"),
            geometry=coords,
            distance_meters=int(data["distance_meters"]),
            duration_seconds=int(data["duration_seconds"]),
            raw_response_ref=data.get("raw_response_ref"),
        )