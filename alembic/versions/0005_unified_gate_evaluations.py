"""Add immutable gate evaluations and current projection binding.

Revision ID: 0005_unified_gate_evaluations
Revises: 0004_prefect_approval_scope
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_unified_gate_evaluations"
down_revision = "0004_prefect_approval_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "gate_evaluations",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("evaluation_key", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("gate_id", sa.String(128), nullable=False),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("adapter_id", sa.String(128), nullable=False),
        sa.Column("adapter_version", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.String(128), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("source_artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="RESTRICT")),
        sa.Column("source_manifest_sha256", sa.String(64)),
        sa.Column("source_contract", sa.String(128), nullable=False),
        sa.Column("evidence_artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="RESTRICT")),
        sa.Column("evidence_manifest_sha256", sa.String(64)),
        sa.Column("expected", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("observed", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checks", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("limitations", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_contracts", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_evaluation_ids", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("origin_pipeline_run_id", sa.String(64), sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL")),
        sa.Column("origin_stage_run_id", sa.String(64), sa.ForeignKey("stage_runs.id", ondelete="SET NULL")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("outcome IN ('PASSED','FAILED')", name="ck_gate_evaluations_outcome_allowed"),
        sa.UniqueConstraint("evaluation_key", name="uq_gate_evaluations_key"),
    )
    op.create_index("ix_gate_evaluations_scope_time", "gate_evaluations", ["gate_id", "scope_type", "scope_id", "evaluated_at"])
    op.create_index("ix_gate_evaluations_source_artifact", "gate_evaluations", ["source_artifact_id"])
    op.create_index("ix_gate_evaluations_evidence_artifact", "gate_evaluations", ["evidence_artifact_id"])
    op.create_index("ix_gate_evaluations_adapter_policy", "gate_evaluations", ["adapter_id", "adapter_version", "policy_id", "policy_version"])

    op.add_column("gate_results", sa.Column("evaluation_outcome", sa.String(32)))
    op.add_column("gate_results", sa.Column("effective_status", sa.String(32)))
    op.add_column("gate_results", sa.Column("current_evaluation_id", sa.String(96), sa.ForeignKey("gate_evaluations.id", ondelete="RESTRICT")))
    op.add_column("gate_results", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_check_constraint("ck_gate_results_evaluation_outcome_allowed", "gate_results", "evaluation_outcome IS NULL OR evaluation_outcome IN ('PASSED','FAILED')")
    op.create_check_constraint("ck_gate_results_effective_status_allowed", "gate_results", "effective_status IS NULL OR effective_status IN ('PENDING','PASSED','FAILED','WAIVED')")

    # Existing gate rows are legacy projections. They remain queryable but do not
    # pretend to have immutable semantic evaluations until deterministic backfill.
    op.execute("UPDATE gate_results SET effective_status = status")
    op.execute("UPDATE gate_results SET evaluation_outcome = status WHERE status IN ('PASSED','FAILED')")


def downgrade() -> None:
    op.drop_constraint("ck_gate_results_effective_status_allowed", "gate_results", type_="check")
    op.drop_constraint("ck_gate_results_evaluation_outcome_allowed", "gate_results", type_="check")
    op.drop_column("gate_results", "updated_at")
    op.drop_column("gate_results", "current_evaluation_id")
    op.drop_column("gate_results", "effective_status")
    op.drop_column("gate_results", "evaluation_outcome")
    op.drop_index("ix_gate_evaluations_adapter_policy", table_name="gate_evaluations")
    op.drop_index("ix_gate_evaluations_evidence_artifact", table_name="gate_evaluations")
    op.drop_index("ix_gate_evaluations_source_artifact", table_name="gate_evaluations")
    op.drop_index("ix_gate_evaluations_scope_time", table_name="gate_evaluations")
    op.drop_table("gate_evaluations")
