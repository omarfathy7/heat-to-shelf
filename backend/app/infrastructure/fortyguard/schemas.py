"""FortyGuard response schemas with strict GeoJSON/unit validation.

The provider contract is normalized: every heatmap response is a GeoJSON
FeatureCollection of polygon tiles carrying at least a tile id, a temperature
in Celsius, and an observation timestamp. Missing, malformed, or out-of-band
values are explicit provider errors (`FORTYGUARD_RESPONSE_INVALID`) — never
silently substituted.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.errors import AppError, ErrorCode

# Plausible Celsius band. Values outside it are treated as a unit/scale mix-up
# (e.g. Fahrenheit) rather than genuine heat — never accepted silently.
MIN_PLAUSIBLE_TEMP_C = -40.0
MAX_PLAUSIBLE_TEMP_C = 70.0

# A tile coordinate is (longitude, latitude) per WGS84. Coordinates that fall
# outside these ranges indicate reversed or invalid ordering.
MAX_LATITUDE = 90.0
MAX_LONGITUDE = 180.0


def _invalid(message: str) -> AppError:
    return AppError(
        ErrorCode.FORTYGUARD_RESPONSE_INVALID,
        message,
        status_code=502,
    )


class TileGeometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]]

    @model_validator(mode="after")
    def _polygon_well_formed(self) -> "TileGeometry":
        ring = self.coordinates[0] if self.coordinates else []
        if len(ring) < 4:
            raise _invalid("tile polygon must have a closed ring of at least 4 points")
        if ring[0] != ring[-1]:
            raise _invalid("tile polygon ring is not closed")
        for lon, lat in ring:
            if not (-MAX_LONGITUDE <= lon <= MAX_LONGITUDE):
                raise _invalid(f"tile longitude out of WGS84 range: {lon}")
            if not (-MAX_LATITUDE <= lat <= MAX_LATITUDE):
                raise _invalid(f"tile latitude out of WGS84 range: {lat}")
        return self


class TileProperties(BaseModel):
    tile_id: str
    temperature_c: float
    observed_at_utc: datetime
    quality: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("temperature_c")
    @classmethod
    def _celsius_band(cls, value: float) -> float:
        if not (MIN_PLAUSIBLE_TEMP_C <= value <= MAX_PLAUSIBLE_TEMP_C):
            raise _invalid(
                f"temperature {value} is outside the plausible Celsius band "
                f"[{MIN_PLAUSIBLE_TEMP_C}, {MAX_PLAUSIBLE_TEMP_C}]"
            )
        return value

    @field_validator("observed_at_utc")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _invalid("observation timestamp must be timezone-aware (UTC)")
        return value


class HeatmapFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: TileProperties
    geometry: TileGeometry


class HeatmapResponse(BaseModel):
    """Raw FortyGuard heatmap as a GeoJSON FeatureCollection."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HeatmapFeature]

    @field_validator("features")
    @classmethod
    def _non_empty(cls, value: list[HeatmapFeature]) -> list[HeatmapFeature]:
        if not value:
            raise _invalid("heatmap FeatureCollection has no features")
        return value


def is_stale(
    observed_at_utc: datetime,
    reference_time: datetime,
    max_staleness_minutes: int,
) -> bool:
    """True when an observation predates the reference by more than the window."""
    return (reference_time - observed_at_utc).total_seconds() > max_staleness_minutes * 60