"""thermal observations

Revision ID: 0002_thermal_observations
Revises: 0001_initial_schema
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002_thermal_observations"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thermal_observations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("segment_id", UUID(as_uuid=True), sa.ForeignKey("route_segments.id"), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("threshold_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("exceedance_hours", sa.Float(), nullable=True),
        sa.Column("persistence_hours", sa.Float(), nullable=True),
        sa.Column("relative_humidity", sa.Float(), nullable=True),
        sa.Column("wet_bulb_temp_c", sa.Float(), nullable=True),
        sa.Column("solar_irradiance_w", sa.Float(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_request_hash", sa.String(64), nullable=False),
        sa.Column("data_quality", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_thermal_observations_segment_id",
        "thermal_observations",
        ["segment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_thermal_observations_segment_id", table_name="thermal_observations")
    op.drop_table("thermal_observations")