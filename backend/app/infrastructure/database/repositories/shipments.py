from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.shipment import Shipment, ShipmentStatus
from app.domain.value_objects.coordinates import Coordinate
from app.domain.value_objects.place import Place
from app.infrastructure.database.geo import coords_from, point_wkt
from app.infrastructure.database.models import Shipment as ShipmentORM


class ShipmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_domain(row: ShipmentORM) -> Shipment:
        org = coords_from(row.origin_point)[0]
        dst = coords_from(row.destination_point)[0]
        return Shipment(
            id=row.id,
            user_id=row.user_id,
            product_profile_id=row.product_profile_id,
            origin=Place(
                label=row.origin_label,
                coordinate=Coordinate(longitude=org[0], latitude=org[1]),
            ),
            destination=Place(
                label=row.destination_label,
                coordinate=Coordinate(longitude=dst[0], latitude=dst[1]),
            ),
            departure_time_utc=row.departure_time_utc,
            status=row.status,
            estimated_duration_seconds=row.estimated_duration_seconds,
            distance_meters=row.distance_meters,
            error_code=row.error_code,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def create(self, shipment: Shipment) -> Shipment:
        row = ShipmentORM(
            user_id=shipment.user_id,
            product_profile_id=shipment.product_profile_id,
            origin_label=shipment.origin.label,
            origin_point=point_wkt(*shipment.origin.coordinate.as_tuple()),
            destination_label=shipment.destination.label,
            destination_point=point_wkt(*shipment.destination.coordinate.as_tuple()),
            departure_time_utc=shipment.departure_time_utc,
            status=shipment.status.value,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return self._to_domain(row)

    def get(self, shipment_id: UUID) -> Shipment | None:
        row = self.session.get(ShipmentORM, shipment_id)
        return self._to_domain(row) if row else None

    def get_owned(self, shipment_id: UUID, user_id: UUID) -> Shipment | None:
        row = self.session.execute(
            select(ShipmentORM).where(ShipmentORM.id == shipment_id, ShipmentORM.user_id == user_id)
        ).scalar_one_or_none()
        return self._to_domain(row) if row else None

    def update_status(
        self,
        shipment: Shipment,
        status: ShipmentStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        estimated_duration_seconds: int | None = None,
        distance_meters: int | None = None,
    ) -> Shipment:
        row = self.session.get(ShipmentORM, shipment.id)
        if row is None:
            return shipment
        row.status = status.value
        row.error_code = error_code
        row.error_message = error_message
        if estimated_duration_seconds is not None:
            row.estimated_duration_seconds = estimated_duration_seconds
        if distance_meters is not None:
            row.distance_meters = distance_meters
        self.session.flush()
        self.session.refresh(row)
        return self._to_domain(row)