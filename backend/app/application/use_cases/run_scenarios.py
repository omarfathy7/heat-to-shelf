import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.use_cases.calculate_risk import CalculateRiskUseCase
from app.application.use_cases.get_shipment import GetShipmentUseCase
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.domain.entities.product import ProductProfile
from app.domain.entities.recommendation import Recommendation
from app.domain.entities.risk_assessment import RiskAssessment
from app.domain.entities.scenario import ScenarioStatus
from app.domain.interfaces.providers import TemperatureProvider
from app.domain.services.cargo_risk import RiskBands, RiskWeights, calculate_risk
from app.domain.services.corridor import route_bbox
from app.domain.services.exposure import SegmentExposureInput, compute_exposure
from app.domain.services.observation_builder import build_observation
from app.domain.services.recommendation import RecommendationDraft, build_recommendation
from app.domain.services.scenario_comparison import ScenarioOutcome, rank_scenarios
from app.domain.services.time_alignment import nearest_sample, sample_request_times
from app.infrastructure.database.geo import coords_from
from app.infrastructure.database.repositories.products import ProductProfileRepository
from app.infrastructure.database.repositories.risk import RiskRepository
from app.infrastructure.database.repositories.routes import RouteRepository
from app.infrastructure.database.repositories.scenarios import (
    RecommendationRepository,
    ScenarioRepository,
)
from app.infrastructure.fortyguard.adapter import FortyGuardTemperatureProvider

logger = logging.getLogger("app.application")


@dataclass
class ScenarioEvaluation:
    id: UUID
    departure_time_utc: datetime
    status: ScenarioStatus
    rank: int | None = None
    outcome: ScenarioOutcome | None = None


@dataclass
class ScenarioRunResult:
    baseline: RiskAssessment
    evaluations: list[ScenarioEvaluation] = field(default_factory=list)
    recommendation: RecommendationDraft | None = None


class RunScenariosUseCase:
    """Evaluate candidate departure times against the persisted journey.

    Reuses the exact exposure + risk engines over the same route; only the
    sampling times shift with each departure time. Baseline risk is
    recomputed deterministically from the persisted journey. Scenario
    observations are transient — only the scenario row, its assessment, and
    the final recommendation are persisted.
    """

    def __init__(
        self,
        session: Session,
        temperature_provider: TemperatureProvider | None = None,
        weights: RiskWeights | None = None,
        bands: RiskBands | None = None,
    ) -> None:
        self.session = session
        self.profiles = ProductProfileRepository(session)
        self.routes = RouteRepository(session)
        self.risk = RiskRepository(session)
        self.scenarios = ScenarioRepository(session)
        self.recommendations = RecommendationRepository(session)
        self.temperature = temperature_provider or FortyGuardTemperatureProvider()
        self.weights = weights or RiskWeights(
            peak_temperature=settings.risk_weight_peak_temperature,
            duration=settings.risk_weight_duration,
            persistence=settings.risk_weight_persistence,
            high_risk_segments=settings.risk_weight_high_risk_segments,
        )
        self.bands = bands or RiskBands(
            warning_at=settings.risk_band_warning_at,
            high_at=settings.risk_band_high_at,
            critical_at=settings.risk_band_critical_at,
        )

    async def execute(
        self,
        shipment_id: UUID,
        user_id: UUID,
        departure_times: list[datetime],
    ) -> ScenarioRunResult:
        operation_start = time.perf_counter()
        try:
            result = await self._run(shipment_id, user_id, departure_times)
        except AppError as exc:
            logger.warning(
                "operation_failed",
                extra={
                    "operation": "scenarios",
                    "shipment_id": str(shipment_id),
                    "error_code": exc.code.value,
                    "error_message": exc.message,
                },
            )
            raise
        logger.info(
            "operation_completed",
            extra={
                "operation": "scenarios",
                "shipment_id": str(shipment_id),
                "duration_ms": round((time.perf_counter() - operation_start) * 1000, 2),
                "scenario_count": len(result.evaluations),
                "completed_count": sum(
                    1 for e in result.evaluations if e.status == ScenarioStatus.COMPLETED
                ),
                "failed_count": sum(
                    1 for e in result.evaluations if e.status == ScenarioStatus.FAILED
                ),
                "recommended_score": (
                    result.recommendation.recommended_score
                    if result.recommendation
                    else None
                ),
            },
        )
        return result

    async def _run(
        self,
        shipment_id: UUID,
        user_id: UUID,
        departure_times: list[datetime],
    ) -> ScenarioRunResult:
        shipment = GetShipmentUseCase(self.session).execute(shipment_id, user_id)
        profile_orm = self.profiles.get(shipment.product_profile_id)
        if profile_orm is None:
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                "product profile no longer available",
                status_code=404,
            )
        profile = ProductProfile.model_validate(profile_orm, from_attributes=True)

        self._validate_times(departure_times, shipment.departure_time_utc)

        route_row = self.routes.get_for_shipment(shipment_id)
        if route_row is None:
            raise AppError(
                ErrorCode.THERMAL_DATA_MISSING,
                "shipment has no route to reuse for scenarios",
                status_code=422,
            )
        segment_rows = self.routes.get_segments_for_route(route_row.id)
        if not segment_rows:
            raise AppError(
                ErrorCode.ANALYSIS_FAILED,
                "route has no segments to analyze",
                status_code=502,
            )
        route = self.routes.route_to_domain(route_row)
        aoi = route_bbox(route)

        # Idempotent rerun: fully replace prior scenario outputs.
        self.recommendations.delete_for_shipment(shipment_id)
        self.scenarios.delete_for_shipment(shipment_id)
        self.risk.delete_for_shipment(shipment_id)
        baseline = CalculateRiskUseCase(self.session).execute(shipment_id, user_id)

        evaluations: list[ScenarioEvaluation] = []
        completed: list[ScenarioOutcome] = []
        for candidate in departure_times:
            scenario = self.scenarios.create(shipment_id, candidate)
            try:
                outcome = await self._evaluate_one(
                    shipment_id=shipment_id,
                    scenario_id=scenario.id,
                    candidate=candidate,
                    original_departure=shipment.departure_time_utc,
                    profile=profile,
                    segment_rows=segment_rows,
                    aoi=aoi,
                )
            except AppError:
                self.scenarios.set_status(scenario.id, ScenarioStatus.FAILED)
                evaluations.append(
                    ScenarioEvaluation(
                        id=scenario.id,
                        departure_time_utc=candidate,
                        status=ScenarioStatus.FAILED,
                    )
                )
                continue
            self.scenarios.set_status(scenario.id, ScenarioStatus.COMPLETED)
            completed.append(outcome)
            evaluations.append(
                ScenarioEvaluation(
                    id=scenario.id,
                    departure_time_utc=candidate,
                    status=ScenarioStatus.COMPLETED,
                    outcome=outcome,
                )
            )

        ranked = rank_scenarios(completed)
        for ranked_outcome in ranked:
            self.scenarios.set_rank(ranked_outcome.id, ranked_outcome.rank)
        evaluations.sort(key=lambda ev: ev.departure_time_utc)

        if not ranked:
            raise AppError(
                ErrorCode.ANALYSIS_FAILED,
                "none of the candidate departure times could be evaluated",
                status_code=502,
            )

        recommended_outcome = ranked[0]
        original = ScenarioOutcome(
            id=None,
            departure_time_utc=shipment.departure_time_utc,
            score=baseline.score,
            level=baseline.level,
            components=baseline.inputs_snapshot.get("components", {}),
            peak_temperature_c=baseline.peak_temperature_c,
            time_above_threshold_hours=baseline.time_above_threshold_hours,
            longest_persistence_hours=baseline.longest_persistence_hours,
            high_risk_segment_count=baseline.high_risk_segment_count,
        )
        draft = build_recommendation(original=original, recommended=recommended_outcome)
        recommendation = Recommendation(
            shipment_id=shipment_id,
            recommended_scenario_id=recommended_outcome.id,
            reason_codes=draft.reason_codes,
            explanation_factors=draft.explanation_factors,
            original_score=draft.original_score,
            recommended_score=draft.recommended_score,
            exposure_reduction_percent=draft.exposure_reduction_percent,
        )
        self.recommendations.create(recommendation)

        by_id = {ev.id: ev for ev in evaluations}
        evaluations = []
        for outcome in ranked:
            ev = by_id[outcome.id]
            evaluations.append(
                ScenarioEvaluation(
                    id=ev.id,
                    departure_time_utc=ev.departure_time_utc,
                    status=ev.status,
                    rank=outcome.rank,
                    outcome=outcome,
                )
            )
        for ev in by_id.values():
            if ev.outcome is None:
                evaluations.append(ev)

        return ScenarioRunResult(
            baseline=baseline,
            evaluations=evaluations,
            recommendation=draft,
        )

    async def _evaluate_one(
        self,
        *,
        shipment_id: UUID,
        scenario_id: UUID,
        candidate: datetime,
        original_departure: datetime,
        profile: ProductProfile,
        segment_rows,
        aoi,
    ) -> ScenarioOutcome:
        offset = candidate - original_departure
        arrivals = [seg.estimated_arrival_utc + offset for seg in segment_rows]
        last_arrival = arrivals[-1]
        sample_times = sample_request_times(
            candidate,
            last_arrival,
            arrivals,
            settings.max_heatmap_requests,
        )

        inputs: list[SegmentExposureInput] = []
        for seg, arrival in zip(segment_rows, arrivals):
            sample_at = nearest_sample(
                arrival,
                sample_times,
                settings.time_alignment_tolerance_minutes,
            )
            request_hash = ""
            tiles = []
            if sample_at is not None:
                request_hash = self._request_hash(aoi, sample_at)
                heatmap = await self.temperature.get_heatmap(aoi, sample_at)
                tiles = heatmap.tiles
            observation = build_observation(
                segment_id=seg.id,
                segment_coords=coords_from(seg.geometry),
                arrival_utc=arrival,
                sample_time_utc=sample_at,
                tiles=tiles,
                min_temp_c=profile.min_temp_c,
                max_temp_c=profile.max_temp_c,
                warning_threshold_c=profile.warning_threshold_c,
                critical_threshold_c=profile.critical_threshold_c,
                alignment_tolerance_minutes=settings.time_alignment_tolerance_minutes,
                request_hash=request_hash,
            )
            inputs.append(
                SegmentExposureInput(
                    sequence=seg.sequence,
                    status=observation.threshold_status,
                    duration_seconds=seg.duration_seconds,
                    temperature_c=observation.temperature_c,
                    recorded_exceedance_hours=observation.exceedance_hours,
                    recorded_persistence_hours=observation.persistence_hours,
                )
            )

        exposure = compute_exposure(inputs)
        result = calculate_risk(exposure, profile, self.weights, self.bands, segment_inputs=inputs)
        assessment = self.risk.create(
            RiskAssessment(
                shipment_id=shipment_id,
                scenario_id=scenario_id,
                score=result.score,
                level=result.level,
                peak_temperature_c=result.peak_temperature_c,
                time_above_threshold_hours=result.time_above_threshold_hours,
                longest_persistence_hours=result.longest_persistence_hours,
                high_risk_segment_count=result.high_risk_segment_count,
                calculation_version=settings.risk_calculation_version,
                inputs_snapshot=self._snapshot(profile, exposure, result),
                explanation_factors=result.explanation_factors,
            )
        )
        self.scenarios.set_assessment(scenario_id, assessment.id)
        return ScenarioOutcome(
            id=scenario_id,
            departure_time_utc=candidate,
            score=result.score,
            level=result.level,
            components=result.components,
            peak_temperature_c=result.peak_temperature_c,
            time_above_threshold_hours=result.time_above_threshold_hours,
            longest_persistence_hours=result.longest_persistence_hours,
            high_risk_segment_count=result.high_risk_segment_count,
        )

    @staticmethod
    def _validate_times(candidates: list[datetime], departure: datetime) -> None:
        horizon = timedelta(hours=settings.scenario_horizon_hours)
        for candidate in candidates:
            if abs(candidate - departure) > horizon:
                raise AppError(
                    ErrorCode.INVALID_TIME_WINDOW,
                    f"departure time must be within {settings.scenario_horizon_hours}h of the shipment departure",
                    status_code=422,
                )

    def _snapshot(self, profile: ProductProfile, exposure, result) -> dict:
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
            "calculation_version": settings.risk_calculation_version,
        }

    @staticmethod
    def _request_hash(aoi, sample_at) -> str:
        raw = json.dumps(
            {"bbox": aoi.model_dump(), "time": sample_at.isoformat()},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()