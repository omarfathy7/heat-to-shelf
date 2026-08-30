"""risk assessments

Revision ID: 0003_risk_assessments
Revises: 0002_thermal_observations
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003_risk_assessments"
down_revision: Union[str, None] = "0002_thermal_observations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", UUID(as_uuid=True), sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("scenario_id", UUID(as_uuid=True), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("peak_temperature_c", sa.Float(), nullable=True),
        sa.Column("time_above_threshold_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("longest_persistence_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("high_risk_segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exposure_reduction_percent", sa.Float(), nullable=True),
        sa.Column("calculation_version", sa.String(20), nullable=False),
        sa.Column("inputs_snapshot", JSONB(), nullable=False),
        sa.Column("explanation_factors", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_risk_assessments_shipment_id",
        "risk_assessments",
        ["shipment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_shipment_id", table_name="risk_assessments")
    op.drop_table("risk_assessments")