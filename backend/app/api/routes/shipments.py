from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user, get_db
from app.api.rate_limit import check_analysis_rate
from app.application.dto.journey import AnalyzeResponse, ThermalJourneyResponse
from app.application.dto.risk import RiskResponse
from app.application.dto.scenario import (
    RecommendationResponse,
    ScenarioRequest,
    ScenarioResultResponse,
    ScenarioRunResponse,
)
from app.application.dto.shipment import CreateShipmentRequest, ShipmentResponse
from app.application.use_cases.analyze_shipment import AnalyzeShipmentUseCase
from app.application.use_cases.calculate_risk import CalculateRiskUseCase
from app.application.use_cases.create_shipment import CreateShipmentUseCase
from app.application.use_cases.get_shipment import GetShipmentUseCase
from app.application.use_cases.get_thermal_journey import GetThermalJourneyUseCase
from app.application.use_cases.run_scenarios import RunScenariosUseCase
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.domain.entities.product import ProductProfile
from app.domain.entities.shipment import Shipment
from app.domain.services.cargo_risk import RiskBands, RiskWeights, calculate_risk
from app.domain.services.exposure import SegmentExposureInput, compute_exposure
from app.domain.value_objects.thermal_observation import ThresholdStatus
from app.infrastructure.database.repositories.observations import ThermalObservationRepository
from app.infrastructure.database.repositories.products import ProductProfileRepository
from app.infrastructure.database.repositories.risk import RiskRepository
from app.infrastructure.database.repositories.routes import RouteRepository
from app.infrastructure.database.repositories.scenarios import (
    RecommendationRepository,
    ScenarioRepository,
)
from app.infrastructure.database.repositories.shipments import ShipmentRepository

router = APIRouter(tags=["shipments"])


def _to_response(shipment: Shipment) -> ShipmentResponse:
    return ShipmentResponse(
        id=shipment.id,
        product_id=shipment.product_profile_id,
        origin={
            "label": shipment.origin.label,
            "coordinate": shipment.origin.coordinate.as_geojson(),
        },
        destination={
            "label": shipment.destination.label,
            "coordinate": shipment.destination.coordinate.as_geojson(),
        },
        departure_time_utc=shipment.departure_time_utc,
        status=shipment.status,
        estimated_duration_seconds=shipment.estimated_duration_seconds,
        distance_meters=shipment.distance_meters,
        error_code=shipment.error_code,
        error_message=shipment.error_message,
        created_at=shipment.created_at,
        updated_at=shipment.updated_at,
    )


@router.post("/shipments", status_code=201, response_model=ShipmentResponse)
async def create_shipment(
    payload: CreateShipmentRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> ShipmentResponse:
    shipment = CreateShipmentUseCase(db).execute(user.id, payload)
    return _to_response(shipment)


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> ShipmentResponse:
    shipment = GetShipmentUseCase(db).execute(shipment_id, user.id)
    return _to_response(shipment)


@router.post("/shipments/{shipment_id}/analyze", status_code=202, response_model=AnalyzeResponse)
async def analyze_shipment(
    shipment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
    _: None = Depends(check_analysis_rate),
) -> AnalyzeResponse:
    shipment_id, developed, observed = await AnalyzeShipmentUseCase(db).execute(shipment_id, user.id)
    return AnalyzeResponse(
        shipment_id=shipment_id,
        status=GetShipmentUseCase(db).execute(shipment_id, user.id).status,
        developed_segments=developed,
        observed_segments=observed,
    )


@router.get("/shipments/{shipment_id}/thermal-journey", response_model=ThermalJourneyResponse)
async def get_thermal_journey(
    shipment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> ThermalJourneyResponse:
    return GetThermalJourneyUseCase(db).execute(shipment_id, user.id)


def _risk_response(assessment) -> RiskResponse:
    snapshot = assessment.inputs_snapshot or {}
    return RiskResponse(
        shipment_id=assessment.shipment_id,
        scenario_id=assessment.scenario_id,
        score=assessment.score,
        level=assessment.level,
        components=snapshot.get("components", {}),
        peak_temperature_c=assessment.peak_temperature_c,
        time_above_threshold_hours=assessment.time_above_threshold_hours,
        longest_persistence_hours=assessment.longest_persistence_hours,
        high_risk_segment_count=assessment.high_risk_segment_count,
        exposure_reduction_percent=assessment.exposure_reduction_percent,
        calculation_version=assessment.calculation_version,
        explanation_factors=assessment.explanation_factors,
        created_at=assessment.created_at,
    )


@router.get("/shipments/{shipment_id}/risk", response_model=RiskResponse)
async def get_shipment_risk(
    shipment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> RiskResponse:
    assessment = CalculateRiskUseCase(db).execute(shipment_id, user.id)
    return _risk_response(assessment)


@router.post("/shipments/{shipment_id}/scenarios", response_model=ScenarioRunResponse)
async def run_scenarios(
    shipment_id: UUID,
    payload: ScenarioRequest,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
    _: None = Depends(check_analysis_rate),
) -> ScenarioRunResponse:
    result = await RunScenariosUseCase(db).execute(
        shipment_id, user.id, payload.departure_times
    )
    draft = result.recommendation
    scenarios = [
        ScenarioResultResponse(
            id=ev.id,
            departure_time_utc=ev.departure_time_utc,
            status=ev.status,
            rank=ev.rank,
            is_recommended=bool(
                draft and ev.id == draft.recommended_scenario_id
            ),
            score=ev.outcome.score if ev.outcome else None,
            level=ev.outcome.level if ev.outcome else None,
            components=ev.outcome.components if ev.outcome else {},
            peak_temperature_c=ev.outcome.peak_temperature_c if ev.outcome else None,
            time_above_threshold_hours=(
                ev.outcome.time_above_threshold_hours if ev.outcome else 0.0
            ),
            longest_persistence_hours=(
                ev.outcome.longest_persistence_hours if ev.outcome else 0.0
            ),
            high_risk_segment_count=(
                ev.outcome.high_risk_segment_count if ev.outcome else 0
            ),
        )
        for ev in result.evaluations
    ]
    recommendation = RecommendationResponse(
        shipment_id=shipment_id,
        recommended_scenario_id=draft.recommended_scenario_id,
        recommended_departure_time_utc=draft.recommended_departure_time_utc,
        original_score=draft.original_score,
        recommended_score=draft.recommended_score,
        exposure_reduction_percent=draft.exposure_reduction_percent,
        original_level=draft.original_level,
        recommended_level=draft.recommended_level,
        level_improved=bool(draft.explanation_factors.get("level_improved")),
        reason_codes=draft.reason_codes,
        explanation_factors=draft.explanation_factors,
    )
    return ScenarioRunResponse(
        shipment_id=shipment_id,
        baseline=_risk_response(result.baseline),
        scenarios=scenarios,
        recommendation=recommendation,
    )


@router.get("/shipments/{shipment_id}/recommendation", response_model=RecommendationResponse)
async def get_shipment_recommendation(
    shipment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> RecommendationResponse:
    GetShipmentUseCase(db).execute(shipment_id, user.id)
    recommendation = RecommendationRepository(db).latest_for_shipment(shipment_id)
    if recommendation is None:
        raise AppError(
            ErrorCode.RECOMMENDATION_UNAVAILABLE,
            "no recommendation has been produced for this shipment yet",
            status_code=404,
        )
    scenario = ScenarioRepository(db).get(recommendation.recommended_scenario_id)
    if scenario is None:
        raise AppError(
            ErrorCode.RECOMMENDATION_UNAVAILABLE,
            "recommendation references a missing scenario",
            status_code=404,
        )
    factors = recommendation.explanation_factors or {}
    return RecommendationResponse(
        id=recommendation.id,
        shipment_id=shipment_id,
        recommended_scenario_id=recommendation.recommended_scenario_id,
        recommended_departure_time_utc=scenario.departure_time_utc,
        original_score=recommendation.original_score,
        recommended_score=recommendation.recommended_score,
        exposure_reduction_percent=recommendation.exposure_reduction_percent,
        original_level=ThresholdStatus(factors.get("original_level", "safe")),
        recommended_level=ThresholdStatus(factors.get("recommended_level", "safe")),
        level_improved=bool(factors.get("level_improved", False)),
        reason_codes=recommendation.reason_codes,
        explanation_factors=factors,
        created_at=recommendation.created_at,
    )


class AssessResponse(BaseModel):
    model_config = {"from_attributes": True}

    study_date: str
    hour: str
    score: float
    level: ThresholdStatus
    components: dict = {}
    peak_temperature_c: float | None = None
    time_above_threshold_hours: float = 0.0
    longest_persistence_hours: float = 0.0
    high_risk_segment_count: int = 0
    segment_count: int = 0
    explanation_factors: dict = {}


@router.get("/assess", response_model=AssessResponse)
async def assess_risk(
    study_date: date = Query(..., description="Study date (YYYY-MM-DD)"),
    hour: str = Query(..., description="Hour (HH:MM)"),
    db=Depends(get_db),
) -> AssessResponse:
    """Risk assessment for a study date/hour window.

    Queries thermal observations within the specified hour and computes
    a deterministic risk score using the current weight configuration.
    """
    try:
        h, m = map(int, hour.split(":"))
        start = datetime.combine(study_date, time(h, m, tzinfo=timezone.utc))
    except (ValueError, AttributeError):
        raise AppError(
            ErrorCode.INVALID_TIME_WINDOW,
            "hour must be in HH:MM format",
            status_code=422,
        )
    end = start.replace(minute=start.minute + 1) if start.minute < 59 else start.replace(minute=0, hour=start.hour + 1)

    observations_repo = ThermalObservationRepository(db)
    pairs = observations_repo.list_by_datetime_window(start, end)

    if not pairs:
        raise AppError(
            ErrorCode.THERMAL_DATA_MISSING,
            "no thermal observations found for the specified study window",
            status_code=422,
        )

    # Resolve product profile via shipment -> route -> segment chain
    routes_repo = RouteRepository(db)
    shipments_repo = ShipmentRepository(db)
    profiles_repo = ProductProfileRepository(db)

    profile = None
    seen_shipments: set[str] = set()
    for segment, _ in pairs:
        route = routes_repo.get(segment.route_id)
        if route is None or route.shipment_id in seen_shipments:
            continue
        seen_shipments.add(route.shipment_id)
        shipment = shipments_repo.get(route.shipment_id)
        if shipment is None:
            continue
        profile_orm = profiles_repo.get(shipment.product_profile_id)
        if profile_orm is not None:
            profile = ProductProfile.model_validate(profile_orm, from_attributes=True)
            break

    if profile is None:
        raise AppError(
            ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
            "no product profile found for observations in this window",
            status_code=422,
        )

    inputs: list[SegmentExposureInput] = []
    for segment, observation in pairs:
        status = ThresholdStatus(observation.threshold_status)
        inputs.append(
            SegmentExposureInput(
                sequence=segment.sequence,
                status=status,
                duration_seconds=segment.duration_seconds,
                temperature_c=observation.temperature_c,
                recorded_exceedance_hours=observation.exceedance_hours,
                recorded_persistence_hours=observation.persistence_hours,
            )
        )

    exposure = compute_exposure(inputs)
    weights = RiskWeights(
        peak_temperature=settings.risk_weight_peak_temperature,
        duration=settings.risk_weight_duration,
        persistence=settings.risk_weight_persistence,
        high_risk_segments=settings.risk_weight_high_risk_segments,
    )
    bands = RiskBands(
        warning_at=settings.risk_band_warning_at,
        high_at=settings.risk_band_high_at,
        critical_at=settings.risk_band_critical_at,
    )
    result = calculate_risk(exposure, profile, weights, bands, segment_inputs=inputs)

    return AssessResponse(
        study_date=study_date.isoformat(),
        hour=hour,
        score=result.score,
        level=result.level,
        components=result.components,
        peak_temperature_c=result.peak_temperature_c,
        time_above_threshold_hours=result.time_above_threshold_hours,
        longest_persistence_hours=result.longest_persistence_hours,
        high_risk_segment_count=result.high_risk_segment_count,
        segment_count=len(inputs),
        explanation_factors=result.explanation_factors,
    )