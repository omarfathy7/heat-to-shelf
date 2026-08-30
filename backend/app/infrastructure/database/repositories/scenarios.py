from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.entities.recommendation import Recommendation
from app.domain.entities.scenario import Scenario, ScenarioStatus
from app.infrastructure.database.models import Recommendation as RecommendationORM
from app.infrastructure.database.models import Scenario as ScenarioORM


class ScenarioRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_domain(row: ScenarioORM) -> Scenario:
        return Scenario(
            id=row.id,
            shipment_id=row.shipment_id,
            departure_time_utc=row.departure_time_utc,
            status=ScenarioStatus(row.status),
            risk_assessment_id=row.risk_assessment_id,
            rank=row.rank,
            created_at=row.created_at,
        )

    def create(
        self,
        shipment_id: UUID,
        departure_time_utc: datetime,
        status: ScenarioStatus = ScenarioStatus.PENDING,
    ) -> Scenario:
        row = ScenarioORM(
            shipment_id=shipment_id,
            departure_time_utc=departure_time_utc,
            status=status.value,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return self._to_domain(row)

    def set_status(self, scenario_id: UUID, status: ScenarioStatus) -> None:
        row = self.session.get(ScenarioORM, scenario_id)
        if row is not None:
            row.status = status.value

    def set_assessment(self, scenario_id: UUID, assessment_id: UUID) -> None:
        row = self.session.get(ScenarioORM, scenario_id)
        if row is not None:
            row.risk_assessment_id = assessment_id

    def set_rank(self, scenario_id: UUID, rank: int) -> None:
        row = self.session.get(ScenarioORM, scenario_id)
        if row is not None:
            row.rank = rank

    def get(self, scenario_id: UUID) -> Scenario | None:
        row = self.session.get(ScenarioORM, scenario_id)
        return self._to_domain(row) if row else None

    def list_for_shipment(self, shipment_id: UUID) -> list[Scenario]:
        rows = (
            self.session.execute(
                select(ScenarioORM)
                .where(ScenarioORM.shipment_id == shipment_id)
                .order_by(ScenarioORM.rank, ScenarioORM.created_at)
            )
            .scalars()
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def delete_for_shipment(self, shipment_id: UUID) -> None:
        self.session.execute(
            delete(ScenarioORM).where(ScenarioORM.shipment_id == shipment_id)
        )


class RecommendationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_domain(row: RecommendationORM) -> Recommendation:
        return Recommendation(
            id=row.id,
            shipment_id=row.shipment_id,
            recommended_scenario_id=row.recommended_scenario_id,
            reason_codes=row.reason_codes or [],
            explanation_factors=row.explanation_factors or {},
            original_score=row.original_score,
            recommended_score=row.recommended_score,
            exposure_reduction_percent=row.exposure_reduction_percent,
            created_at=row.created_at,
        )

    def create(self, recommendation: Recommendation) -> Recommendation:
        row = RecommendationORM(
            shipment_id=recommendation.shipment_id,
            recommended_scenario_id=recommendation.recommended_scenario_id,
            reason_codes=recommendation.reason_codes,
            explanation_factors=recommendation.explanation_factors,
            original_score=recommendation.original_score,
            recommended_score=recommendation.recommended_score,
            exposure_reduction_percent=recommendation.exposure_reduction_percent,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return self._to_domain(row)

    def latest_for_shipment(self, shipment_id: UUID) -> Recommendation | None:
        row = self.session.execute(
            select(RecommendationORM)
            .where(RecommendationORM.shipment_id == shipment_id)
            .order_by(RecommendationORM.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return self._to_domain(row) if row else None

    def delete_for_shipment(self, shipment_id: UUID) -> None:
        self.session.execute(
            delete(RecommendationORM).where(RecommendationORM.shipment_id == shipment_id)
        )