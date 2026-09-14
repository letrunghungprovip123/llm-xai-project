"""promotion and waiver policy

Revision ID: 0006_promotion_and_waiver_policy
Revises: 0005_unified_gate_evaluations
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from research.python.researchops.ops_core.db.types import JSON_DOCUMENT

revision = "0006_promotion_and_waiver_policy"
down_revision = "0005_unified_gate_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gate_waivers",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("gate_result_id", sa.String(length=96), nullable=False),
        sa.Column("evaluation_id", sa.String(length=96), nullable=False),
        sa.Column("gate_id", sa.String(length=128), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", sa.String(length=160), nullable=False),
        sa.Column("policy_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.String(length=96), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.String(length=255)),
        sa.Column("revocation_reason", sa.Text()),
        sa.CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED')", name="ck_gate_waivers_status_allowed"),
        sa.ForeignKeyConstraint(["gate_result_id"], ["gate_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_id"], ["gate_evaluations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("request_key", name="uq_gate_waivers_request_key"),
    )
    op.create_index("ix_gate_waivers_scope_status", "gate_waivers", ["scope_type", "scope_id", "gate_id", "status"])
    op.create_index("ix_gate_waivers_evaluation", "gate_waivers", ["evaluation_id"])

    op.create_table(
        "promotion_decisions",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("target_kind", sa.String(length=128), nullable=False),
        sa.Column("policy_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("policy_sha256", sa.String(length=64), nullable=False),
        sa.Column("expected_state", sa.String(length=64), nullable=False),
        sa.Column("target_state", sa.String(length=64), nullable=False),
        sa.Column("gate_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("approval_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("waiver_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_external_state", JSON_DOCUMENT, nullable=False),
        sa.Column("new_external_state", JSON_DOCUMENT, nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("executed_by", sa.String(length=255)),
        sa.Column("approval_id", sa.String(length=96)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("decision IN ('APPROVED','DENIED')", name="ck_promotion_decisions_decision_allowed"),
        sa.CheckConstraint("execution_status IN ('PENDING','COMPLETED','FAILED','FAILED_PARTIAL')", name="ck_promotion_decisions_execution_status_allowed"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_promotion_decisions_key"),
    )
    op.create_index("ix_promotion_decisions_target", "promotion_decisions", ["target_type", "target_id"])
    op.create_index("ix_promotion_decisions_policy", "promotion_decisions", ["policy_id", "policy_version"])


def downgrade() -> None:
    op.drop_index("ix_promotion_decisions_policy", table_name="promotion_decisions")
    op.drop_index("ix_promotion_decisions_target", table_name="promotion_decisions")
    op.drop_table("promotion_decisions")
    op.drop_index("ix_gate_waivers_evaluation", table_name="gate_waivers")
    op.drop_index("ix_gate_waivers_scope_status", table_name="gate_waivers")
    op.drop_table("gate_waivers")
