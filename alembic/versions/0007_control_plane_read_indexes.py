"""Add control-plane keyset pagination indexes.

Revision ID: 0007_control_plane_read_indexes
Revises: 0006_promotion_and_waiver_policy
"""
from alembic import op

revision = "0007_control_plane_read_indexes"
down_revision = "0006_promotion_and_waiver_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_pipeline_runs_created_id", "pipeline_runs", ["created_at", "id"])
    op.create_index("ix_artifacts_created_id", "artifacts", ["created_at", "id"])
    op.create_index("ix_releases_created_id", "releases", ["created_at", "id"])
    op.create_index("ix_gate_results_updated_id", "gate_results", ["updated_at", "id"])
    op.create_index("ix_approvals_requested_id", "approvals", ["requested_at", "id"])
    op.create_index("ix_promotion_decisions_created_id", "promotion_decisions", ["created_at", "id"])
    op.create_index("ix_audit_events_occurred_id", "audit_events", ["occurred_at", "id"])
    op.create_index("ix_run_events_occurred_id", "run_events", ["occurred_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_run_events_occurred_id", table_name="run_events")
    op.drop_index("ix_audit_events_occurred_id", table_name="audit_events")
    op.drop_index("ix_promotion_decisions_created_id", table_name="promotion_decisions")
    op.drop_index("ix_approvals_requested_id", table_name="approvals")
    op.drop_index("ix_gate_results_updated_id", table_name="gate_results")
    op.drop_index("ix_releases_created_id", table_name="releases")
    op.drop_index("ix_artifacts_created_id", table_name="artifacts")
    op.drop_index("ix_pipeline_runs_created_id", table_name="pipeline_runs")
