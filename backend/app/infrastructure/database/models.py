from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProductProfile(Base):
    __tablename__ = "product_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    min_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    max_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    warning_threshold_c: Mapped[float] = mapped_column(Float, nullable=False)
    critical_threshold_c: Mapped[float] = mapped_column(Float, nullable=False)
    exposure_rules = mapped_column(JSONB, nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_profile_id: Mapped[str] = mapped_column(ForeignKey("product_profiles.id"), nullable=False)
    origin_label: Mapped[str] = mapped_column(String(200), nullable=False)
    origin_point = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    destination_label: Mapped[str] = mapped_column(String(200), nullable=False)
    destination_point = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    departure_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    estimated_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_route_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geometry = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    route_points = mapped_column(JSONB, nullable=False)
    raw_response_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RouteSegment(Base):
    __tablename__ = "route_segments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)
    start_distance_meters: Mapped[float] = mapped_column(Float, nullable=False)
    end_distance_meters: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_arrival_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class ThermalObservation(Base):
    __tablename__ = "thermal_observations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    segment_id: Mapped[str] = mapped_column(ForeignKey("route_segments.id"), nullable=False)
    observed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    exceedance_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    wet_bulb_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    solar_irradiance_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_quality = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    peak_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_above_threshold_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    longest_persistence_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    high_risk_segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exposure_reduction_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculation_version: Mapped[str] = mapped_column(String(20), nullable=False)
    inputs_snapshot = mapped_column(JSONB, nullable=False)
    explanation_factors = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    departure_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    risk_assessment_id: Mapped[str | None] = mapped_column(
        ForeignKey("risk_assessments.id"), nullable=True
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    recommended_scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id"), nullable=False
    )
    reason_codes = mapped_column(JSONB, nullable=False)
    explanation_factors = mapped_column(JSONB, nullable=False)
    original_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_score: Mapped[float] = mapped_column(Float, nullable=False)
    exposure_reduction_percent: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())