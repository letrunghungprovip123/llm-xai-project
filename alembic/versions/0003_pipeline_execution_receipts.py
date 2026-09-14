"""Add immutable pipeline execution receipt bindings.

Revision ID: 0003_pipeline_receipts
Revises: 0002_prefect_orchestration
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_pipeline_receipts"
down_revision = "0002_prefect_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_run_receipts",
        sa.Column(
            "pipeline_run_id",
            sa.String(64),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "artifact_id",
            sa.String(160),
            sa.ForeignKey("artifacts.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_pipeline_run_receipts_artifact",
        "pipeline_run_receipts",
        ["artifact_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pipeline_run_receipts_artifact",
        table_name="pipeline_run_receipts",
    )
    op.drop_table("pipeline_run_receipts")
