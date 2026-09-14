"""Add Prefect orchestration bindings and named stage outputs.

Revision ID: 0002_prefect_orchestration
Revises: 0001_researchops_core
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_prefect_orchestration"
down_revision = "0001_researchops_core"
branch_labels = None
depends_on = None

J = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "orchestration_bindings",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("orchestrator", sa.String(32), nullable=False),
        sa.Column("orchestrator_version", sa.String(64), nullable=False),
        sa.Column(
            "pipeline_run_id",
            sa.String(64),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage_run_id",
            sa.String(72),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
        ),
        sa.Column("prefect_flow_run_id", sa.String(64), nullable=False),
        sa.Column("prefect_task_run_id", sa.String(64)),
        sa.Column("deployment_name", sa.String(255)),
        sa.Column("work_pool_name", sa.String(255)),
        sa.Column("work_queue_name", sa.String(255)),
        sa.Column("orchestration_key", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("metadata", J, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "orchestrator",
            "prefect_flow_run_id",
            "prefect_task_run_id",
            "attempt_number",
            name="uq_orchestration_bindings_prefect_run_attempt",
        ),
        sa.UniqueConstraint(
            "orchestrator",
            "orchestration_key",
            "attempt_number",
            name="uq_orchestration_bindings_key_attempt",
        ),
    )
    op.create_index(
        "ix_orchestration_bindings_pipeline_stage",
        "orchestration_bindings",
        ["pipeline_run_id", "stage_run_id"],
    )
    op.create_index(
        "ix_orchestration_bindings_prefect_flow",
        "orchestration_bindings",
        ["prefect_flow_run_id"],
    )

    op.create_table(
        "stage_run_outputs",
        sa.Column(
            "stage_run_id",
            sa.String(72),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("output_name", sa.String(128), primary_key=True),
        sa.Column("contract", sa.String(128), nullable=False),
        sa.Column(
            "artifact_id",
            sa.String(160),
            sa.ForeignKey("artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "stage_run_id",
            "artifact_id",
            name="uq_stage_run_outputs_artifact",
        ),
    )
    op.create_index(
        "ix_stage_run_outputs_artifact",
        "stage_run_outputs",
        ["artifact_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stage_run_outputs_artifact", table_name="stage_run_outputs")
    op.drop_table("stage_run_outputs")
    op.drop_index(
        "ix_orchestration_bindings_prefect_flow",
        table_name="orchestration_bindings",
    )
    op.drop_index(
        "ix_orchestration_bindings_pipeline_stage",
        table_name="orchestration_bindings",
    )
    op.drop_table("orchestration_bindings")
