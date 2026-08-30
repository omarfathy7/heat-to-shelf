from datetime import datetime
from enum import Enum
from uuid import UUID


class ScenarioStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Scenario:
    def __init__(
        self,
        shipment_id: UUID,
        departure_time_utc: datetime,
        id: UUID | None = None,
        status: ScenarioStatus = ScenarioStatus.PENDING,
        risk_assessment_id: UUID | None = None,
        rank: int | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.shipment_id = shipment_id
        self.departure_time_utc = departure_time_utc
        self.status = status
        self.risk_assessment_id = risk_assessment_id
        self.rank = rank
        self.created_at = created_at