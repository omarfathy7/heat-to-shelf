from uuid import UUID

from sqlalchemy.orm import Session

from app.application.dto.shipment import CreateShipmentRequest, ShipmentResponse
from app.core.errors import AppError, ErrorCode
from app.domain.entities.product import ProductProfile
from app.domain.entities.shipment import Shipment
from app.infrastructure.database.repositories.products import ProductProfileRepository
from app.infrastructure.database.repositories.shipments import ShipmentRepository


class CreateShipmentUseCase:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.profiles = ProductProfileRepository(session)
        self.shipments = ShipmentRepository(session)

    def execute(self, user_id: UUID, request: CreateShipmentRequest) -> Shipment:
        profile_orm = self.profiles.get_active_for_product(request.product_id)
        if profile_orm is None:
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                "no active sourced profile for this product",
                status_code=404,
            )
        profile = ProductProfile.model_validate(profile_orm, from_attributes=True)
        if not profile.is_approved():
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                "product profile is not approved (source pending)",
                status_code=422,
            )

        origin = request.origin.to_place()
        destination = request.destination.to_place()
        shipment = Shipment(
            user_id=user_id,
            product_profile_id=profile.id,
            origin=origin,
            destination=destination,
            departure_time_utc=request.departure_time,
        )
        saved = self.shipments.create(shipment)
        return saved