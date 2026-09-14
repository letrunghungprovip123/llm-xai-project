"""Create ResearchOps operational core schema.

Revision ID: 0001_researchops_core
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_researchops_core"
down_revision = None
branch_labels = None
depends_on = None

RUN_STATES = "'PENDING','WAITING_APPROVAL','RUNNING','SUCCEEDED','FAILED','CANCELLED'"
ARTIFACT_STATES = "'DRAFT','UPLOADED','VERIFIED','CERTIFIED','REJECTED','SUPERSEDED'"
RELEASE_STATES = "'DRAFT','CANDIDATE','READY_WITH_LIMITATIONS','CERTIFIED','REJECTED','SUPERSEDED'"
GATE_STATES = "'PENDING','PASSED','FAILED','WAIVED'"
APPROVAL_STATES = "'REQUESTED','APPROVED','REJECTED','EXPIRED'"
J = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table("environment_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("python_version", sa.String(64), nullable=False),
        sa.Column("node_version", sa.String(64)),
        sa.Column("operating_system", sa.String(128), nullable=False),
        sa.Column("architecture", sa.String(64), nullable=False),
        sa.Column("dependency_lock_sha256", sa.String(64), nullable=False),
        sa.Column("container_image_digest", sa.String(255)),
        sa.Column("git_commit", sa.String(64), nullable=False),
        sa.Column("git_dirty", sa.Boolean(), nullable=False),
        sa.Column("details", J, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table("pipeline_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flow_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("registry_sha256", sa.String(64), nullable=False),
        sa.Column("source_commit", sa.String(64), nullable=False),
        sa.Column("environment_snapshot_id", sa.String(64), sa.ForeignKey("environment_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("parameters", J, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("error_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN ({RUN_STATES})", name="ck_pipeline_runs_status_allowed"),
        sa.UniqueConstraint("idempotency_key", name="uq_pipeline_runs_idempotency_key"),
    )
    op.create_index("ix_pipeline_runs_status_created", "pipeline_runs", ["status", "created_at"])
    op.create_table("stage_runs",
        sa.Column("id", sa.String(72), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(64), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", sa.String(128), nullable=False),
        sa.Column("stage_version", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("command_snapshot", J, nullable=False),
        sa.Column("approval_policy", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("stdout_artifact_id", sa.String(160)),
        sa.Column("stderr_artifact_id", sa.String(160)),
        sa.Column("error_type", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN ({RUN_STATES})", name="ck_stage_runs_status_allowed"),
        sa.UniqueConstraint("pipeline_run_id", "stage_id", "attempt", name="uq_stage_runs_attempt"),
    )
    op.create_index("ix_stage_runs_pipeline_status", "stage_runs", ["pipeline_run_id", "status"])
    op.create_table("run_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("pipeline_run_id", sa.String(64), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_run_id", sa.String(72), sa.ForeignKey("stage_runs.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", J, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_run_events_run_occurred", "run_events", ["pipeline_run_id", "occurred_at"])
    op.create_table("artifacts",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("artifact_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("manifest_uri", sa.String(1024), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("producer_stage_run_id", sa.String(72), sa.ForeignKey("stage_runs.id", ondelete="RESTRICT")),
        sa.Column("source_commit", sa.String(64), nullable=False),
        sa.Column("environment_snapshot_id", sa.String(64), sa.ForeignKey("environment_snapshots.id", ondelete="RESTRICT")),
        sa.Column("limitations", J, nullable=False),
        sa.Column("metadata", J, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN ({ARTIFACT_STATES})", name="ck_artifacts_status_allowed"),
        sa.UniqueConstraint("manifest_sha256", name="uq_artifacts_manifest_sha256"),
    )
    op.create_index("ix_artifacts_type_status_created", "artifacts", ["artifact_type", "status", "created_at"])
    op.create_index("ix_artifacts_producer_stage_run", "artifacts", ["producer_stage_run_id"])
    op.create_table("artifact_files",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("object_uri", sa.String(2048), nullable=False),
        sa.Column("object_version_id", sa.String(255)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger()),
        sa.Column("column_count", sa.Integer()),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.UniqueConstraint("artifact_id", "relative_path", name="uq_artifact_files_path"),
    )
    op.create_table("lineage_edges",
        sa.Column("parent_artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("child_artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("relationship_type", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("parent_artifact_id <> child_artifact_id", name="ck_lineage_edges_no_self_edge"),
    )
    op.create_index("ix_lineage_edges_child", "lineage_edges", ["child_artifact_id"])
    op.create_table("releases",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("release_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("manifest_artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_commit", sa.String(64), nullable=False),
        sa.Column("parent_release_id", sa.String(160), sa.ForeignKey("releases.id", ondelete="RESTRICT")),
        sa.Column("limitations", J, nullable=False),
        sa.Column("metadata", J, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN ({RELEASE_STATES})", name="ck_releases_status_allowed"),
    )
    op.create_index("ix_releases_type_status_created", "releases", ["release_type", "status", "created_at"])
    op.create_table("release_artifacts",
        sa.Column("release_id", sa.String(160), sa.ForeignKey("releases.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("artifact_id", sa.String(160), sa.ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("role", sa.String(128), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table("gate_results",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("gate_id", sa.String(128), nullable=False),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("expected", J, nullable=False),
        sa.Column("observed", J, nullable=False),
        sa.Column("details", J, nullable=False),
        sa.Column("source_contracts", J, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN ({GATE_STATES})", name="ck_gate_results_status_allowed"),
        sa.UniqueConstraint("gate_id", "scope_type", "scope_id", name="uq_gate_results_scope"),
    )
    op.create_index("ix_gate_results_scope_blocking_status", "gate_results", ["scope_type", "scope_id", "blocking", "status"])
    op.create_table("approvals",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("policy", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", sa.String(255)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN ({APPROVAL_STATES})", name="ck_approvals_status_allowed"),
    )
    op.create_index("ix_approvals_status_requested", "approvals", ["status", "requested_at"])
    op.create_table("audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.Column("before_state", J),
        sa.Column("after_state", J),
        sa.Column("metadata", J, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_target_occurred", "audit_events", ["target_type", "target_id", "occurred_at"])


def downgrade() -> None:
    for table in [
        "audit_events", "approvals", "gate_results", "release_artifacts", "releases",
        "lineage_edges", "artifact_files", "artifacts", "run_events", "stage_runs",
        "pipeline_runs", "environment_snapshots",
    ]:
        op.drop_table(table)
