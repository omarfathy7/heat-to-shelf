from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.domain.entities.shipment import Shipment
from app.infrastructure.database.repositories.shipments import ShipmentRepository


class GetShipmentUseCase:
    def __init__(self, session: Session) -> None:
        self.shipments = ShipmentRepository(session)

    def execute(self, shipment_id: UUID, user_id: UUID) -> Shipment:
        shipment = self.shipments.get_owned(shipment_id, user_id)
        if shipment is None:
            raise AppError(
                ErrorCode.SHIPMENT_NOT_FOUND,
                "shipment not found",
                status_code=404,
            )
        return shipment