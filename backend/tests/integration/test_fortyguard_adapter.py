import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

import httpx
import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.bounding_box import BoundingBox
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.fortyguard.adapter import FortyGuardTemperatureProvider
from app.infrastructure.fortyguard.client import FortyGuardClient
from app.infrastructure.cache.cache import TTLCache

FIXTURES = Path(__file__).parents[1] / "fixtures" / "fortyguard"
CALLS: dict[str, int] = {}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def make_adapter(handler) -> FortyGuardTemperatureProvider:
    transport = httpx.MockTransport(handler)
    client = FortyGuardClient(
        api_key="test-key",
        base_url="https://fortyguard.test",
        timeout=2.0,
        max_retries=2,
        backoff_seconds=0.0,
        max_staleness_minutes=60,
        transport=transport,
    )
    return FortyGuardTemperatureProvider(client=client, cache=TTLCache(ttl_seconds=300))


def json_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, headers={"x-ratelimit-remaining": "1000", "x-ratelimit-limit": "5000"})


def bbox() -> BoundingBox:
    return BoundingBox(min_lon=-122.60, min_lat=37.20, max_lon=-121.95, max_lat=37.90)


@pytest.mark.anyio
class TestFortyGuardAdapter:
    async def test_heatmap_normalizes_tiles(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            CALLS["heatmap"] = CALLS.get("heatmap", 0) + 1
            return json_response(load("heatmap_valid.json"))

        provider = make_adapter(handler)
        obs = datetime(2026, 8, 21, 19, tzinfo=timezone.utc)
        data = await provider.get_heatmap(bbox(), obs)

        assert data.source == "fortyguard"
        assert len(data.tiles) == 2
        assert data.tiles[0].temperature_c == 28.4
        assert data.tiles[0].longitude == pytest.approx(-121.88, abs=0.01)
        assert data.tiles[0].latitude == pytest.approx(37.35, abs=0.01)
        assert data.request_metadata["provider"] == "fortyguard"
        assert data.request_metadata["status"] == 200

    async def test_heatmap_stale_marked_not_dropped(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return json_response(load("heatmap_stale.json"))

        provider = make_adapter(handler)
        obs = datetime(2026, 8, 21, 19, tzinfo=timezone.utc)
        data = await provider.get_heatmap(bbox(), obs)
        tile = data.tiles[0]
        assert tile.data_quality["stale"] is True
        assert tile.data_quality["stale_minutes"] == 1440.0

    async def test_cached_response_hits_once(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return json_response(load("heatmap_valid.json"))

        provider = make_adapter(handler)
        obs = datetime(2026, 8, 21, 19, tzinfo=timezone.utc)
        a = await provider.get_heatmap(bbox(), obs)
        b = await provider.get_heatmap(bbox(), obs)
        assert a is b
        assert calls["count"] == 1

    async def test_retry_on_429_then_success(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] <= 2:
                return httpx.Response(429, json={"error": "rate limited"})
            return json_response(load("heatmap_valid.json"))

        provider = make_adapter(handler)
        obs = datetime(2026, 8, 21, 19, tzinfo=timezone.utc)
        data = await provider.get_heatmap(bbox(), obs)
        assert calls["count"] == 3
        assert data.request_metadata["retries"] == 2
        assert data.request_metadata["rate_limited"] is True

    async def test_provider_5xx_maps_to_sanitized_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"internal": "secret-stack-trace"})

        provider = make_adapter(handler)
        with pytest.raises(AppError) as exc:
            await provider.get_heatmap(bbox(), datetime(2026, 8, 21, 12, tzinfo=timezone.utc))
        assert exc.value.code == ErrorCode.FORTYGUARD_PROVIDER_FAILED
        assert "secret-stack-trace" not in exc.value.message

    async def test_timeout_after_retries(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("upstream slow")

        provider = make_adapter(handler)
        with pytest.raises(AppError) as exc:
            await provider.get_heatmap(bbox(), datetime(2026, 8, 21, 12, tzinfo=timezone.utc))
        assert exc.value.code == ErrorCode.FORTYGUARD_PROVIDER_FAILED
        assert exc.value.status_code == 504

    async def test_non_json_body_maps_to_invalid_response(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>proxy error</html>")

        provider = make_adapter(handler)
        with pytest.raises(AppError) as exc:
            await provider.get_heatmap(bbox(), datetime(2026, 8, 21, 12, tzinfo=timezone.utc))
        assert exc.value.code == ErrorCode.FORTYGUARD_RESPONSE_INVALID

    async def test_exceedance_persistence_environment_shape(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/v1/exceedance":
                return json_response({"items": [{"tile_id": "t1", "minutes_above_threshold": 45}]})
            if path == "/v1/persistence":
                return json_response({"items": [{"tile_id": "t1", "longest_persistence_minutes": 22}]})
            return json_response({"readings": [{"longitude": -122.0, "latitude": 37.5, "relative_humidity": 55.0}]})

        provider = make_adapter(handler)
        period = TimeWindow(
            start_utc=datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
            end_utc=datetime(2026, 8, 21, 22, tzinfo=timezone.utc),
        )
        ex = await provider.get_exceedance(bbox(), 30.0, period)
        assert ex.items[0].minutes_above_threshold == 45
        per = await provider.get_persistence(bbox(), 30.0, period)
        assert per.items[0].longest_persistence_minutes == 22
        env = await provider.get_environment([Coordinate(longitude=-122.0, latitude=37.5)], period)
        assert env.readings[0].relative_humidity == 55.0

    async def test_unconfigured_client_fails_cleanly(self) -> None:
        client = FortyGuardClient(api_key=None, base_url="https://x.test")
        provider = FortyGuardTemperatureProvider(client=client)
        with pytest.raises(AppError) as exc:
            await provider.get_heatmap(bbox(), datetime(2026, 8, 21, 12, tzinfo=timezone.utc))
        assert exc.value.code == ErrorCode.FORTYGUARD_PROVIDER_FAILED
        assert exc.value.status_code == 503