import hashlib
import json

from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.domain.interfaces.providers import TemperatureProvider
from app.domain.value_objects.bounding_box import BoundingBox
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.thermal import (
    EnvironmentData,
    EnvironmentalReading,
    ExceedanceData,
    ExceedanceItem,
    HeatmapData,
    PersistenceData,
    PersistenceItem,
    ThermalTile,
)
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.cache.cache import TTLCache
from app.infrastructure.fortyguard.client import FortyGuardClient
from app.infrastructure.fortyguard.schemas import HeatmapResponse, is_stale

SOURCE = "fortyguard"


class FortyGuardTemperatureProvider(TemperatureProvider):
    """TemperatureProvider implementation backed by FortyGuard.

    Never called from API route handlers; API talks to use cases only.
    """

    def __init__(
        self,
        client: FortyGuardClient | None = None,
        cache: TTLCache | None = None,
        max_staleness_minutes: int | None = None,
    ) -> None:
        self._client = client or FortyGuardClient()
        self._cache = cache or TTLCache(settings.fortyguard_cache_ttl_seconds)
        self.max_staleness_minutes = (
            max_staleness_minutes
            if max_staleness_minutes is not None
            else settings.fortyguard_max_staleness_minutes
        )

    # ----- cache helpers -----

    @staticmethod
    def _key(kind: str, payload: dict) -> str:
        raw = json.dumps({"kind": kind, **payload}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    # ----- heatmap -----

    async def get_heatmap(self, aoi: BoundingBox, observation_time) -> HeatmapData:
        params = {
            "min_x": aoi.min_lon,
            "min_y": aoi.min_lat,
            "max_x": aoi.max_lon,
            "max_y": aoi.max_lat,
            "time": observation_time.isoformat(),
        }
        cache_key = self._key("heatmap", {"bbox": aoi.model_dump(), "time": observation_time})
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        body, meta = await self._client.get_json(SOURCE, "/v1/heatmap", params)
        try:
            response = HeatmapResponse.model_validate(body)
        except ValidationError as exc:
            raise AppError(
                ErrorCode.FORTYGUARD_RESPONSE_INVALID,
                "fortyguard heatmap response failed validation",
                status_code=502,
                details={"errors": exc.errors()[:10]},
            ) from exc

        tiles: list[ThermalTile] = []
        for feature in response.features:
            ring = feature.geometry.coordinates[0]
            centroid_lon = sum(p[0] for p in ring) / len(ring)
            centroid_lat = sum(p[1] for p in ring) / len(ring)
            props = feature.properties
            stale = is_stale(
                props.observed_at_utc,
                observation_time,
                self.max_staleness_minutes,
            )
            tiles.append(
                ThermalTile(
                    tile_id=props.tile_id,
                    longitude=round(centroid_lon, 6),
                    latitude=round(centroid_lat, 6),
                    temperature_c=props.temperature_c,
                    observed_at_utc=props.observed_at_utc,
                    polygon=[(p[0], p[1]) for p in ring],
                    data_quality={
                        "quality": props.quality,
                        "stale": stale,
                        "stale_minutes": (
                            round((observation_time - props.observed_at_utc).total_seconds() / 60, 1)
                            if stale
                            else 0
                        ),
                    },
                )
            )

        result = HeatmapData(
            source=SOURCE,
            observation_time=observation_time,
            bbox=aoi,
            tiles=tiles,
            request_metadata=meta,
        )
        self._cache.set(cache_key, result)
        return result

    # ----- exceedance / persistence / environment -----

    async def get_exceedance(self, aoi: BoundingBox, threshold_c: float, period: TimeWindow) -> ExceedanceData:
        params = {
            "min_x": aoi.min_lon,
            "min_y": aoi.min_lat,
            "max_x": aoi.max_lon,
            "max_y": aoi.max_lat,
            "threshold_c": threshold_c,
            "start": period.start_utc.isoformat(),
            "end": period.end_utc.isoformat(),
        }
        cache_key = self._key(
            "exceedance",
            {"bbox": aoi.model_dump(), "threshold_c": threshold_c, "period": period.model_dump()},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        body, meta = await self._client.get_json(SOURCE, "/v1/exceedance", params)
        items = [
            ExceedanceItem(tile_id=row["tile_id"], minutes_above_threshold=float(row["minutes_above_threshold"]))
            for row in body.get("items", [])
        ]
        result = ExceedanceData(
            source=SOURCE,
            threshold_c=threshold_c,
            period=period,
            items=items,
            request_metadata=meta,
        )
        self._cache.set(cache_key, result)
        return result

    async def get_persistence(self, aoi: BoundingBox, threshold_c: float, period: TimeWindow) -> PersistenceData:
        params = {
            "min_x": aoi.min_lon,
            "min_y": aoi.min_lat,
            "max_x": aoi.max_lon,
            "max_y": aoi.max_lat,
            "threshold_c": threshold_c,
            "start": period.start_utc.isoformat(),
            "end": period.end_utc.isoformat(),
        }
        cache_key = self._key(
            "persistence",
            {"bbox": aoi.model_dump(), "threshold_c": threshold_c, "period": period.model_dump()},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        body, meta = await self._client.get_json(SOURCE, "/v1/persistence", params)
        items = [
            PersistenceItem(tile_id=row["tile_id"], longest_persistence_minutes=float(row["longest_persistence_minutes"]))
            for row in body.get("items", [])
        ]
        result = PersistenceData(
            source=SOURCE,
            threshold_c=threshold_c,
            period=period,
            items=items,
            request_metadata=meta,
        )
        self._cache.set(cache_key, result)
        return result

    async def get_environment(self, points: list[Coordinate], period: TimeWindow) -> EnvironmentData:
        coords = [
            [{"longitude": c.longitude, "latitude": c.latitude} for c in points]
        ]
        params = {
            "points": json.dumps(coords),
            "start": period.start_utc.isoformat(),
            "end": period.end_utc.isoformat(),
        }
        cache_key = self._key(
            "environment",
            {"points": [c.model_dump() for c in points], "period": period.model_dump()},
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        body, meta = await self._client.get_json(SOURCE, "/v1/environment", params)
        readings = [
            EnvironmentalReading(
                longitude=float(row["longitude"]),
                latitude=float(row["latitude"]),
                relative_humidity=row.get("relative_humidity"),
                wet_bulb_c=row.get("wet_bulb_c"),
                solar_irradiance_w=row.get("solar_irradiance_w"),
            )
            for row in body.get("readings", [])
        ]
        result = EnvironmentData(source=SOURCE, period=period, readings=readings, request_metadata=meta)
        self._cache.set(cache_key, result)
        return result