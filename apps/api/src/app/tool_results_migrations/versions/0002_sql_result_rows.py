"""Add row projections and metadata for SQL analysis of saved tool results."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "tool_results_0002"
down_revision = "tool_results_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_tool_payloads", sa.Column(
        "observed_schema", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ))
    op.add_column("runtime_tool_payloads", sa.Column("sample", postgresql.JSONB(), nullable=True))
    op.add_column("runtime_tool_payloads", sa.Column(
        "sample_complete", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.add_column("runtime_tool_payloads", sa.Column(
        "schema_complete", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.add_column("runtime_tool_payloads", sa.Column(
        "row_count", sa.Integer(), nullable=False, server_default="0",
    ))
    op.add_column("runtime_tool_payloads", sa.Column("query_sql", sa.Text(), nullable=True))
    op.add_column("runtime_tool_payloads", sa.Column(
        "source_result_ids", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    ))
    op.create_table(
        "runtime_tool_result_rows",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["runtime_tool_payloads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("result_id", "ordinal"),
    )
    op.create_index("ix_tool_result_rows_run", "runtime_tool_result_rows", ["run_id", "result_id"])
    op.execute("""
        UPDATE runtime_tool_payloads
        SET row_count = CASE WHEN jsonb_typeof(payload) = 'array'
                             THEN jsonb_array_length(payload) ELSE 1 END
    """)
    op.execute("""
        INSERT INTO runtime_tool_result_rows (result_id, run_id, ordinal, data)
        SELECT p.id, p.run_id, e.ordinality - 1, e.value
        FROM runtime_tool_payloads p
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(p.payload) = 'array' THEN p.payload
                 ELSE jsonb_build_array(p.payload) END
        ) WITH ORDINALITY AS e(value, ordinality)
    """)


def downgrade() -> None:
    op.drop_index("ix_tool_result_rows_run", table_name="runtime_tool_result_rows")
    op.drop_table("runtime_tool_result_rows")
    op.drop_column("runtime_tool_payloads", "source_result_ids")
    op.drop_column("runtime_tool_payloads", "query_sql")
    op.drop_column("runtime_tool_payloads", "row_count")
    op.drop_column("runtime_tool_payloads", "schema_complete")
    op.drop_column("runtime_tool_payloads", "sample_complete")
    op.drop_column("runtime_tool_payloads", "sample")
    op.drop_column("runtime_tool_payloads", "observed_schema")
