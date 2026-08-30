import hashlib
import json
import logging
import time
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.use_cases.get_shipment import GetShipmentUseCase
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.domain.entities.product import ProductProfile
from app.domain.entities.shipment import ShipmentStatus
from app.domain.interfaces.providers import RoutingProvider, TemperatureProvider
from app.domain.services.corridor import route_bbox
from app.domain.services.observation_builder import build_observation
from app.domain.services.route_segmenter import segment_route
from app.domain.services.time_alignment import sample_request_times, nearest_sample
from app.domain.value_objects.thermal_observation import ThermalObservation
from app.infrastructure.database.geo import coords_from
from app.infrastructure.database.repositories.observations import ThermalObservationRepository
from app.infrastructure.database.repositories.products import ProductProfileRepository
from app.infrastructure.database.repositories.routes import RouteRepository
from app.infrastructure.database.repositories.shipments import ShipmentRepository
from app.infrastructure.fortyguard.adapter import FortyGuardTemperatureProvider
from app.infrastructure.routing.provider import get_routing_provider

logger = logging.getLogger("app.application")


class AnalyzeShipmentUseCase:
    """Route + thermal journey development for a shipment.

    Runs synchronously for the MVP: build/reuse the route, request sampled
    heatmaps from FortyGuard, match tiles to segments, classify against the
    profile, persist observations, and move the shipment to ready (or failed).
    No values are invented for missing or stale tile data.
    """

    def __init__(
        self,
        session: Session,
        routing_provider: RoutingProvider | None = None,
        temperature_provider: TemperatureProvider | None = None,
    ) -> None:
        self.session = session
        self.shipments = ShipmentRepository(session)
        self.routes = RouteRepository(session)
        self.observations = ThermalObservationRepository(session)
        self.profiles = ProductProfileRepository(session)
        self.routing = routing_provider or get_routing_provider()
        self.temperature = temperature_provider or FortyGuardTemperatureProvider()

    async def execute(self, shipment_id: UUID, user_id: UUID) -> tuple[UUID, int, int]:
        shipment = GetShipmentUseCase(self.session).execute(shipment_id, user_id)
        profile_orm = self.profiles.get(shipment.product_profile_id)
        if profile_orm is None:
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                "product profile no longer available",
                status_code=404,
            )
        profile = ProductProfile.model_validate(profile_orm, from_attributes=True)

        try:
            route_row, segment_rows = await self._ensure_route(shipment_id, shipment)
            self.shipments.update_status(shipment, ShipmentStatus.ANALYZING)
            route = self.routes.route_to_domain(route_row)

            departure = shipment.departure_time_utc
            arrivals = [seg.estimated_arrival_utc for seg in segment_rows]
            if not arrivals:
                raise AppError(
                    ErrorCode.ANALYSIS_FAILED,
                    "route has no segments to analyze",
                    status_code=502,
                )
            operation_start = time.perf_counter()
            last_arrival = arrivals[-1]
            sample_times = sample_request_times(
                departure,
                last_arrival,
                arrivals,
                settings.max_heatmap_requests,
            )

            segment_ids = [seg.id for seg in segment_rows]
            self.observations.delete_for_segments(segment_ids)

            observations: list[ThermalObservation] = []
            aoi = route_bbox(route)
            matched = 0
            for seg in segment_rows:
                seg_coords = coords_from(seg.geometry)
                sample_at = nearest_sample(
                    seg.estimated_arrival_utc,
                    sample_times,
                    settings.time_alignment_tolerance_minutes,
                )
                request_hash = ""
                tiles = []
                if sample_at is not None:
                    request_hash = self._request_hash(aoi, sample_at)
                    heatmap = await self.temperature.get_heatmap(aoi, sample_at)
                    tiles = heatmap.tiles
                observation = build_observation(
                    segment_id=seg.id,
                    segment_coords=seg_coords,
                    arrival_utc=seg.estimated_arrival_utc,
                    sample_time_utc=sample_at,
                    tiles=tiles,
                    min_temp_c=profile.min_temp_c,
                    max_temp_c=profile.max_temp_c,
                    warning_threshold_c=profile.warning_threshold_c,
                    critical_threshold_c=profile.critical_threshold_c,
                    alignment_tolerance_minutes=settings.time_alignment_tolerance_minutes,
                    request_hash=request_hash,
                )
                if observation.data_quality.get("matched"):
                    matched += 1
                observations.append(observation)

            self.observations.create_many(observations)
            self.shipments.update_status(
                shipment,
                ShipmentStatus.READY,
                estimated_duration_seconds=route.duration_seconds,
                distance_meters=route.distance_meters,
            )
            logger.info(
                "operation_completed",
                extra={
                    "operation": "analyze",
                    "shipment_id": str(shipment_id),
                    "duration_ms": round((time.perf_counter() - operation_start) * 1000, 2),
                    "status": ShipmentStatus.READY.value,
                    "developed_segments": len(segment_rows),
                    "observed_segments": matched,
                },
            )
            return shipment_id, len(segment_rows), matched
        except AppError as exc:
            self.shipments.update_status(
                shipment,
                ShipmentStatus.FAILED,
                error_code=exc.code.value,
                error_message=exc.message,
            )
            logger.warning(
                "operation_failed",
                extra={
                    "operation": "analyze",
                    "shipment_id": str(shipment_id),
                    "error_code": exc.code.value,
                    "error_message": exc.message,
                },
            )
            raise

    async def _ensure_route(self, shipment_id: UUID, shipment):
        existing = self.routes.get_for_shipment(shipment_id)
        if existing is not None:
            return existing, self.routes.get_segments_for_route(existing.id)
        self.shipments.update_status(shipment, ShipmentStatus.ROUTING)
        try:
            route_data = await self.routing.build_route(
                shipment.origin.coordinate,
                shipment.destination.coordinate,
            )
            segments = segment_route(
                route_data,
                shipment.departure_time_utc,
                settings.route_segment_count,
            )
            route, segment_rows = self.routes.create(shipment_id, route_data, segments)
            return route, segment_rows
        except AppError as exc:
            self.shipments.update_status(
                shipment,
                ShipmentStatus.FAILED,
                error_code=str(exc.code.value),
                error_message=exc.message,
            )
            raise

    @staticmethod
    def _request_hash(aoi, sample_at) -> str:
        raw = json.dumps(
            {"bbox": aoi.model_dump(), "time": sample_at.isoformat()},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()