"""Create the dedicated JSONB store for runtime tool payloads."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "tool_results_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_tool_payloads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("call_id", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(512), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=True),
        sa.Column("agent_execution_id", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("source_total", sa.Integer(), nullable=True),
        sa.Column("source_complete", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "call_id", name="uq_tool_payload_run_call"),
    )
    op.create_index("ix_tool_payload_result_scope", "runtime_tool_payloads", ["id", "run_id", "tenant_id", "user_id"])
    op.create_index("ix_tool_payload_expiry", "runtime_tool_payloads", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_payload_expiry", table_name="runtime_tool_payloads")
    op.drop_index("ix_tool_payload_result_scope", table_name="runtime_tool_payloads")
    op.drop_table("runtime_tool_payloads")
