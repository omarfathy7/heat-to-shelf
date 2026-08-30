from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.value_objects.bounding_box import BoundingBox
from app.domain.value_objects.time_window import TimeWindow


class ThermalTile(BaseModel):
    """One spatially-resolved thermal observation (tile) from a provider heatmap."""

    model_config = ConfigDict(frozen=True)

    tile_id: str
    longitude: float
    latitude: float
    temperature_c: float
    observed_at_utc: datetime
    polygon: list[tuple[float, float]]
    data_quality: dict[str, Any] = {}


class HeatmapData(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    observation_time: datetime
    bbox: BoundingBox
    tiles: list[ThermalTile]
    request_metadata: dict[str, Any] = {}


class ExceedanceItem(BaseModel):
    tile_id: str
    minutes_above_threshold: float


class ExceedanceData(BaseModel):
    source: str
    threshold_c: float
    period: TimeWindow
    items: list[ExceedanceItem]
    request_metadata: dict[str, Any] = {}


class PersistenceItem(BaseModel):
    tile_id: str
    longest_persistence_minutes: float


class PersistenceData(BaseModel):
    source: str
    threshold_c: float
    period: TimeWindow
    items: list[PersistenceItem]
    request_metadata: dict[str, Any] = {}


class EnvironmentalReading(BaseModel):
    longitude: float
    latitude: float
    relative_humidity: float | None = None
    wet_bulb_c: float | None = None
    solar_irradiance_w: float | None = None


class EnvironmentData(BaseModel):
    source: str
    period: TimeWindow
    readings: list[EnvironmentalReading]
    request_metadata: dict[str, Any] = {}