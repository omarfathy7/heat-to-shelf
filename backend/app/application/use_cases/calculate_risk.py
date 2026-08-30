from uuid import UUID

from sqlalchemy.orm import Session

from app.application.use_cases.get_shipment import GetShipmentUseCase
from app.core.config import Settings, settings
from app.core.errors import AppError, ErrorCode
from app.domain.entities.product import ProductProfile
from app.domain.entities.risk_assessment import RiskAssessment
from app.domain.services.cargo_risk import RiskBands, RiskWeights, calculate_risk
from app.domain.services.exposure import SegmentExposureInput, compute_exposure
from app.domain.value_objects.thermal_observation import ThresholdStatus
from app.infrastructure.database.repositories.observations import ThermalObservationRepository
from app.infrastructure.database.repositories.products import ProductProfileRepository
from app.infrastructure.database.repositories.risk import RiskRepository


class CalculateRiskUseCase:
    """Run the deterministic exposure + risk engines on a persisted journey.

    Idempotently persists the baseline assessment (scenario_id = None).
    Pure engines only — no provider calls.
    """

    CALCULATION_VERSION = "1.0.0"

    def __init__(
        self,
        session: Session,
        weights: RiskWeights | None = None,
        bands: RiskBands | None = None,
        calculation_settings: Settings | None = None,
    ) -> None:
        self.session = session
        cfg = calculation_settings or settings
        self.weights = weights or RiskWeights(
            peak_temperature=cfg.risk_weight_peak_temperature,
            duration=cfg.risk_weight_duration,
            persistence=cfg.risk_weight_persistence,
            high_risk_segments=cfg.risk_weight_high_risk_segments,
        )
        self.bands = bands or RiskBands(
            warning_at=cfg.risk_band_warning_at,
            high_at=cfg.risk_band_high_at,
            critical_at=cfg.risk_band_critical_at,
        )
        self.calculation_version = cfg.risk_calculation_version
        self.profiles = ProductProfileRepository(session)
        self.observations = ThermalObservationRepository(session)
        self.risk = RiskRepository(session)

    def execute(self, shipment_id: UUID, user_id: UUID) -> RiskAssessment:
        shipment = GetShipmentUseCase(self.session).execute(shipment_id, user_id)

        profile_orm = self.profiles.get(shipment.product_profile_id)
        if profile_orm is None:
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                "product profile no longer available",
                status_code=404,
            )
        profile = ProductProfile.model_validate(profile_orm, from_attributes=True)

        pairs = self.observations.list_for_shipment(shipment_id)
        if not pairs:
            raise AppError(
                ErrorCode.THERMAL_DATA_MISSING,
                "shipment has no thermal journey to assess",
                status_code=422,
            )

        inputs: list[SegmentExposureInput] = []
        for segment_orm, observation_orm in pairs:
            status = (
                ThresholdStatus(observation_orm.threshold_status)
                if observation_orm is not None
                else ThresholdStatus.UNKNOWN
            )
            inputs.append(
                SegmentExposureInput(
                    sequence=segment_orm.sequence,
                    status=status,
                    duration_seconds=segment_orm.duration_seconds,
                    temperature_c=observation_orm.temperature_c if observation_orm else None,
                    recorded_exceedance_hours=(
                        observation_orm.exceedance_hours if observation_orm else None
                    ),
                    recorded_persistence_hours=(
                        observation_orm.persistence_hours if observation_orm else None
                    ),
                )
            )

        exposure = compute_exposure(inputs)
        result = calculate_risk(exposure, profile, self.weights, self.bands, segment_inputs=inputs)

        assessment = RiskAssessment(
            shipment_id=shipment_id,
            score=result.score,
            level=result.level,
            peak_temperature_c=result.peak_temperature_c,
            time_above_threshold_hours=result.time_above_threshold_hours,
            longest_persistence_hours=result.longest_persistence_hours,
            high_risk_segment_count=result.high_risk_segment_count,
            calculation_version=self.calculation_version,
            inputs_snapshot=self._snapshot(profile, exposure, result),
            explanation_factors=result.explanation_factors,
        )

        self.risk.delete_baselines(shipment_id)
        return self.risk.create(assessment)

    def _snapshot(self, profile, exposure, result) -> dict:
        return {
            "profile_id": str(profile.id),
            "profile_version": profile.version,
            "warning_threshold_c": profile.warning_threshold_c,
            "critical_threshold_c": profile.critical_threshold_c,
            "exposure_rules": profile.exposure_rules,
            "weights": {
                "peak_temperature": self.weights.normalized().peak_temperature,
                "duration": self.weights.normalized().duration,
                "persistence": self.weights.normalized().persistence,
                "high_risk_segments": self.weights.normalized().high_risk_segments,
            },
            "bands": {
                "warning_at": self.bands.warning_at,
                "high_at": self.bands.high_at,
                "critical_at": self.bands.critical_at,
            },
            "exposure": {
                "observed_segment_count": exposure.observed_segment_count,
                "total_segment_count": exposure.total_segment_count,
                "exposed_segment_count": exposure.exposed_segment_count,
                "high_risk_segment_count": exposure.high_risk_segment_count,
                "time_above_warning_hours": exposure.time_above_warning_hours,
                "time_above_critical_hours": exposure.time_above_critical_hours,
                "longest_persistence_hours": exposure.longest_persistence_hours,
                "peak_temperature_c": exposure.peak_temperature_c,
                "average_temperature_c": exposure.average_temperature_c,
                "total_duration_minutes": exposure.total_duration_minutes,
            },
            "components": result.components,
            "calculation_version": self.calculation_version,
        }