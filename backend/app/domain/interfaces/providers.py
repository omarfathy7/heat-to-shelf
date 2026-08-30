from datetime import datetime
from typing import Protocol

from app.domain.value_objects.bounding_box import BoundingBox
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.route import RouteData
from app.domain.value_objects.thermal import (
    EnvironmentData,
    ExceedanceData,
    HeatmapData,
    PersistenceData,
)
from app.domain.value_objects.time_window import TimeWindow


class RoutingProvider(Protocol):
    async def build_route(self, origin: Coordinate, destination: Coordinate) -> RouteData: ...


class TemperatureProvider(Protocol):
    async def get_heatmap(self, aoi: BoundingBox, observation_time: datetime) -> HeatmapData: ...
    async def get_exceedance(self, aoi: BoundingBox, threshold_c: float, period: TimeWindow) -> ExceedanceData: ...
    async def get_persistence(self, aoi: BoundingBox, threshold_c: float, period: TimeWindow) -> PersistenceData: ...
    async def get_environment(self, points: list[Coordinate], period: TimeWindow) -> EnvironmentData: ...