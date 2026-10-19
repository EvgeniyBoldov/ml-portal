"""Persist reusable file representations and plan-independent run context."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0195"
down_revision = "0194"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3
    from app.services.orchestration_prompts import PLANNER_PROMPT_V3, SYNTHESIZER_PROMPT_V3
    for role, prompt in (("turn_preflight", TURN_PREFLIGHT_PROMPT_V3),
                         ("planner", PLANNER_PROMPT_V3), ("synthesizer", SYNTHESIZER_PROMPT_V3)):
        op.execute(sa.text("""UPDATE system_llm_roles SET
            identity=:identity, mission=:mission, rules=:rules, safety=:safety,
            output_requirements=:output_requirements, updated_at=now()
            WHERE role_type=:role AND is_active IS TRUE
        """).bindparams(role=role, **{key: prompt[key] for key in (
            "identity", "mission", "rules", "safety", "output_requirements")}))
    op.create_table("chat_artifact_representations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_id", pg.UUID(as_uuid=True), sa.ForeignKey("chat_artifact_references.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("extraction_key", sa.String(128), nullable=False),
        sa.Column("storage_bucket", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("details", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("artifact_id", "source_fingerprint", "extraction_key", name="uq_chat_artifact_representation_version"))
    op.create_index("ix_chat_artifact_representations_artifact_id", "chat_artifact_representations", ["artifact_id"])
    op.create_table("runtime_run_contexts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", pg.UUID(as_uuid=True), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.String(255), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("manifest", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_runtime_run_contexts_chat_id", "runtime_run_contexts", ["chat_id"])


def downgrade() -> None:
    op.drop_table("runtime_run_contexts")
    op.drop_table("chat_artifact_representations")
