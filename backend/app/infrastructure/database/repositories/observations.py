from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.value_objects.thermal_observation import ThermalObservation
from app.infrastructure.database.models import Route as RouteORM
from app.infrastructure.database.models import RouteSegment as RouteSegmentORM
from app.infrastructure.database.models import ThermalObservation as ObservationORM


class ThermalObservationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_many(self, observations: Sequence[ThermalObservation]) -> None:
        for obs in observations:
            self.session.add(
                ObservationORM(
                    segment_id=obs.segment_id,
                    observed_at_utc=obs.observed_at_utc,
                    latitude=obs.latitude,
                    longitude=obs.longitude,
                    temperature_c=obs.temperature_c,
                    threshold_status=obs.threshold_status.value,
                    exceedance_hours=obs.exceedance_hours,
                    persistence_hours=obs.persistence_hours,
                    relative_humidity=obs.relative_humidity,
                    wet_bulb_temp_c=obs.wet_bulb_temp_c,
                    solar_irradiance_w=obs.solar_irradiance_w,
                    source=obs.source,
                    source_request_hash=obs.source_request_hash,
                    data_quality=obs.data_quality or {},
                )
            )
        self.session.flush()

    def delete_for_segments(self, segment_ids: Sequence[UUID]) -> None:
        if not segment_ids:
            return
        self.session.execute(
            ObservationORM.__table__.delete().where(ObservationORM.segment_id.in_(segment_ids))
        )

    def count_for_segments(self, segment_ids: Sequence[UUID]) -> int:
        if not segment_ids:
            return 0
        return int(
            self.session.execute(
                select(func.count()).select_from(ObservationORM).where(
                    ObservationORM.segment_id.in_(segment_ids)
                )
            ).scalar_one()
        )

    def list_for_shipment(self, shipment_id: UUID) -> list[tuple[RouteSegmentORM, ObservationORM | None]]:
        """Ordered (segment, observation) pairs for a shipment, origin first."""
        rows = self.session.execute(
            select(RouteSegmentORM, ObservationORM)
            .join(RouteORM, RouteSegmentORM.route_id == RouteORM.id)
            .outerjoin(ObservationORM, ObservationORM.segment_id == RouteSegmentORM.id)
            .where(RouteORM.shipment_id == shipment_id)
            .order_by(RouteSegmentORM.sequence)
        ).all()
        return [(segment, observation) for segment, observation in rows]

    def list_by_datetime_window(
        self, start: datetime, end: datetime
    ) -> list[tuple[RouteSegmentORM, ObservationORM]]:
        """Return (segment, observation) pairs where the observation falls within [start, end)."""
        rows = self.session.execute(
            select(RouteSegmentORM, ObservationORM)
            .join(RouteORM, RouteSegmentORM.route_id == RouteORM.id)
            .join(ObservationORM, ObservationORM.segment_id == RouteSegmentORM.id)
            .where(ObservationORM.observed_at_utc >= start)
            .where(ObservationORM.observed_at_utc < end)
            .order_by(RouteSegmentORM.sequence)
        ).all()
        return [(segment, observation) for segment, observation in rows]