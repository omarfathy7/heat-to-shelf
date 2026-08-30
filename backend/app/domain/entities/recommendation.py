from datetime import datetime
from uuid import UUID


class Recommendation:
    def __init__(
        self,
        shipment_id: UUID,
        recommended_scenario_id: UUID,
        reason_codes: list[str],
        explanation_factors: dict,
        original_score: float,
        recommended_score: float,
        exposure_reduction_percent: float,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.shipment_id = shipment_id
        self.recommended_scenario_id = recommended_scenario_id
        self.reason_codes = reason_codes
        self.explanation_factors = explanation_factors
        self.original_score = original_score
        self.recommended_score = recommended_score
        self.exposure_reduction_percent = exposure_reduction_percent
        self.created_at = created_at