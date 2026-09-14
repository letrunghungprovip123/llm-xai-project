"""Add durable API idempotency and control operations.

Revision ID: 0008_control_plane_operations
Revises: 0007_control_plane_read_indexes
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_control_plane_operations"
down_revision = "0007_control_plane_read_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stage_runs", sa.Column("error_category", sa.String(length=64), nullable=True))
    op.add_column("stage_runs", sa.Column("retryable", sa.Boolean(), nullable=True))
    op.create_index(
        "ix_stage_runs_status_retryable",
        "stage_runs",
        ["status", "retryable"],
    )

    op.create_table(
        "api_idempotency_requests",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("principal_subject", sa.String(length=255), nullable=False),
        sa.Column("http_method", sa.String(length=16), nullable=False),
        sa.Column("route_template", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('PROCESSING','COMPLETED','FAILED')", name=op.f("ck_api_idempotency_requests_status_allowed")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_idempotency_requests")),
        sa.UniqueConstraint("principal_subject", "http_method", "route_template", "idempotency_key", name="uq_api_idempotency_request_scope"),
    )
    op.create_index("ix_api_idempotency_created_id", "api_idempotency_requests", ["created_at", "id"])
    op.create_index("ix_api_idempotency_resource", "api_idempotency_requests", ["resource_type", "resource_id"])

    op.create_table(
        "control_operations",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("prefect_flow_run_id", sa.String(length=96), nullable=True),
        sa.Column("pipeline_run_id", sa.String(length=64), nullable=True),
        sa.Column("promotion_decision_id", sa.String(length=96), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_request_id", sa.String(length=96), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','FAILED_PARTIAL','CANCELLED')", name=op.f("ck_control_operations_status_allowed")),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["api_idempotency_requests.id"], name=op.f("fk_control_operations_idempotency_request_id_api_idempotency_requests"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name=op.f("fk_control_operations_pipeline_run_id_pipeline_runs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["promotion_decision_id"], ["promotion_decisions.id"], name=op.f("fk_control_operations_promotion_decision_id_promotion_decisions"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_control_operations")),
    )
    op.create_index("ix_control_operations_status_created", "control_operations", ["status", "created_at"])
    op.create_index("ix_control_operations_target", "control_operations", ["target_type", "target_id"])
    op.create_index("ix_control_operations_prefect", "control_operations", ["prefect_flow_run_id"])
    op.create_index("ix_control_operations_created_id", "control_operations", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_control_operations_created_id", table_name="control_operations")
    op.drop_index("ix_control_operations_prefect", table_name="control_operations")
    op.drop_index("ix_control_operations_target", table_name="control_operations")
    op.drop_index("ix_control_operations_status_created", table_name="control_operations")
    op.drop_table("control_operations")
    op.drop_index("ix_api_idempotency_resource", table_name="api_idempotency_requests")
    op.drop_index("ix_api_idempotency_created_id", table_name="api_idempotency_requests")
    op.drop_table("api_idempotency_requests")
    op.drop_index("ix_stage_runs_status_retryable", table_name="stage_runs")
    op.drop_column("stage_runs", "retryable")
    op.drop_column("stage_runs", "error_category")
