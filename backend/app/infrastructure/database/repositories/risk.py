from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.risk_assessment import RiskAssessment
from app.infrastructure.database.models import RiskAssessment as RiskAssessmentORM


class RiskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_domain(row: RiskAssessmentORM) -> RiskAssessment:
        return RiskAssessment(
            id=row.id,
            shipment_id=row.shipment_id,
            scenario_id=row.scenario_id,
            score=row.score,
            level=row.level,
            peak_temperature_c=row.peak_temperature_c,
            time_above_threshold_hours=row.time_above_threshold_hours,
            longest_persistence_hours=row.longest_persistence_hours,
            high_risk_segment_count=row.high_risk_segment_count,
            exposure_reduction_percent=row.exposure_reduction_percent,
            calculation_version=row.calculation_version,
            inputs_snapshot=row.inputs_snapshot or {},
            explanation_factors=row.explanation_factors or {},
            created_at=row.created_at,
        )

    def create(self, assessment: RiskAssessment) -> RiskAssessment:
        row = RiskAssessmentORM(
            shipment_id=assessment.shipment_id,
            scenario_id=assessment.scenario_id,
            score=assessment.score,
            level=assessment.level.value,
            peak_temperature_c=assessment.peak_temperature_c,
            time_above_threshold_hours=assessment.time_above_threshold_hours,
            longest_persistence_hours=assessment.longest_persistence_hours,
            high_risk_segment_count=assessment.high_risk_segment_count,
            exposure_reduction_percent=assessment.exposure_reduction_percent,
            calculation_version=assessment.calculation_version,
            inputs_snapshot=assessment.inputs_snapshot,
            explanation_factors=assessment.explanation_factors,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return self._to_domain(row)

    def delete_baselines(self, shipment_id: UUID) -> None:
        self.session.execute(
            RiskAssessmentORM.__table__.delete().where(
                RiskAssessmentORM.shipment_id == shipment_id,
                RiskAssessmentORM.scenario_id.is_(None),
            )
        )

    def delete_for_shipment(self, shipment_id: UUID) -> None:
        self.session.execute(
            RiskAssessmentORM.__table__.delete().where(
                RiskAssessmentORM.shipment_id == shipment_id,
            )
        )

    def latest_baseline(self, shipment_id: UUID) -> RiskAssessment | None:
        row = self.session.execute(
            select(RiskAssessmentORM)
            .where(
                RiskAssessmentORM.shipment_id == shipment_id,
                RiskAssessmentORM.scenario_id.is_(None),
            )
            .order_by(RiskAssessmentORM.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return self._to_domain(row) if row else None