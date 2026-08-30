"""scenarios and recommendations

Revision ID: 0004_scenarios_recommendations
Revises: 0003_risk_assessments
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004_scenarios_recommendations"
down_revision: Union[str, None] = "0003_risk_assessments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", UUID(as_uuid=True), sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("departure_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("risk_assessment_id", UUID(as_uuid=True), sa.ForeignKey("risk_assessments.id"), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scenarios_shipment_id", "scenarios", ["shipment_id"])

    op.create_table(
        "recommendations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", UUID(as_uuid=True), sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("recommended_scenario_id", UUID(as_uuid=True), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("reason_codes", JSONB(), nullable=False),
        sa.Column("explanation_factors", JSONB(), nullable=False),
        sa.Column("original_score", sa.Float(), nullable=False),
        sa.Column("recommended_score", sa.Float(), nullable=False),
        sa.Column("exposure_reduction_percent", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_recommendations_shipment_id", "recommendations", ["shipment_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_shipment_id", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_scenarios_shipment_id", table_name="scenarios")
    op.drop_table("scenarios")