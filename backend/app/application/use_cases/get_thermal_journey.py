from uuid import UUID

from sqlalchemy.orm import Session

from app.application.dto.journey import (
    JourneySegmentResponse,
    ObservationResponse,
    ThermalJourneyResponse,
)
from app.application.use_cases.get_shipment import GetShipmentUseCase
from app.infrastructure.database.geo import coords_from
from app.infrastructure.database.repositories.observations import ThermalObservationRepository
from app.infrastructure.database.repositories.routes import RouteRepository


class GetThermalJourneyUseCase:
    """Read the developed thermal journey for an owned shipment.

    Not-yet-analyzed shipments return an empty journey (no fabricated data).
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.routes = RouteRepository(session)
        self.observations = ThermalObservationRepository(session)

    def execute(self, shipment_id: UUID, user_id: UUID) -> ThermalJourneyResponse:
        shipment = GetShipmentUseCase(self.session).execute(shipment_id, user_id)
        route_row = self.routes.get_for_shipment(shipment_id)
        if route_row is None:
            return ThermalJourneyResponse(
                shipment_id=shipment_id,
                status=shipment.status,
                segments=[],
                geojson={"type": "FeatureCollection", "features": []},
            )

        pairs = self.observations.list_for_shipment(shipment_id)
        segments: list[JourneySegmentResponse] = []
        features = []
        for segment_orm, observation_orm in pairs:
            coords = coords_from(segment_orm.geometry)
            midpoint = coords[len(coords) // 2] if coords else (0.0, 0.0)
            observation = None
            if observation_orm is not None:
                observation = ObservationResponse(
                    temperature_c=observation_orm.temperature_c,
                    observed_at_utc=observation_orm.observed_at_utc,
                    threshold_status=observation_orm.threshold_status,
                    latitude=observation_orm.latitude,
                    longitude=observation_orm.longitude,
                    source=observation_orm.source,
                    source_request_hash=observation_orm.source_request_hash,
                    data_quality=observation_orm.data_quality or {},
                )
            status = observation_orm.threshold_status if observation_orm else "missing"
            segments.append(
                JourneySegmentResponse(
                    sequence=segment_orm.sequence,
                    start_distance_meters=segment_orm.start_distance_meters,
                    end_distance_meters=segment_orm.end_distance_meters,
                    estimated_arrival_utc=segment_orm.estimated_arrival_utc,
                    duration_seconds=segment_orm.duration_seconds,
                    midpoint={"longitude": midpoint[0], "latitude": midpoint[1]},
                    observation=observation,
                )
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "sequence": segment_orm.sequence,
                        "threshold_status": status,
                        "temperature_c": observation_orm.temperature_c if observation_orm else None,
                        "observed_at_utc": observation_orm.observed_at_utc if observation_orm else None,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [list(c) for c in coords],
                    },
                }
            )

        return ThermalJourneyResponse(
            shipment_id=shipment_id,
            status=shipment.status,
            segments=segments,
            geojson={"type": "FeatureCollection", "features": features},
        )