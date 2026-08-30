"""initial schema: users, products, profiles, shipments, routes, segments

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2.types import Geometry
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "product_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("min_temp_c", sa.Float(), nullable=False),
        sa.Column("max_temp_c", sa.Float(), nullable=False),
        sa.Column("warning_threshold_c", sa.Float(), nullable=False),
        sa.Column("critical_threshold_c", sa.Float(), nullable=False),
        sa.Column("exposure_rules", JSONB(), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_product_profiles_product_version", "product_profiles", ["product_id", "version"])

    op.create_table(
        "shipments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_profile_id", UUID(as_uuid=True), sa.ForeignKey("product_profiles.id"), nullable=False),
        sa.Column("origin_label", sa.String(200), nullable=False),
        sa.Column("origin_point", Geometry(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("destination_label", sa.String(200), nullable=False),
        sa.Column("destination_point", Geometry(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("departure_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "routes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", UUID(as_uuid=True), sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_route_id", sa.String(100), nullable=True),
        sa.Column("geometry", Geometry(geometry_type="LINESTRING", srid=4326), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("route_points", JSONB(), nullable=False),
        sa.Column("raw_response_ref", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "route_segments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("route_id", UUID(as_uuid=True), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("geometry", Geometry(geometry_type="LINESTRING", srid=4326), nullable=False),
        sa.Column("start_distance_meters", sa.Float(), nullable=False),
        sa.Column("end_distance_meters", sa.Float(), nullable=False),
        sa.Column("estimated_arrival_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("route_segments")
    op.drop_table("routes")
    op.drop_table("shipments")
    op.drop_table("product_profiles")
    op.drop_table("products")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS postgis")