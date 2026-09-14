"""Add Prefect approval scope and idempotency metadata.

Revision ID: 0004_prefect_approval_scope
Revises: 0003_pipeline_receipts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_prefect_approval_scope"
down_revision = "0003_pipeline_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approvals",
        sa.Column(
            "pipeline_run_id",
            sa.String(64),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column("approvals", sa.Column("node_id", sa.String(128), nullable=True))
    op.add_column("approvals", sa.Column("stage_id", sa.String(128), nullable=True))
    op.add_column("approvals", sa.Column("request_key", sa.String(64), nullable=True))
    op.add_column(
        "approvals",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_approvals_pipeline_status",
        "approvals",
        ["pipeline_run_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_approvals_request_key",
        "approvals",
        ["request_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_approvals_request_key", table_name="approvals")
    op.drop_index("ix_approvals_pipeline_status", table_name="approvals")
    op.drop_column("approvals", "details")
    op.drop_column("approvals", "request_key")
    op.drop_column("approvals", "stage_id")
    op.drop_column("approvals", "node_id")
    op.drop_column("approvals", "pipeline_run_id")
