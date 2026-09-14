"""Protect glossary identity and prevent scope-blind global promotion.

Revision ID: 0122
Revises: 0121
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None

_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.drop_index("uq_glossary_entries_scope_term", table_name="glossary_entries")
    op.execute(f"""
        CREATE UNIQUE INDEX uq_glossary_entries_identity
        ON glossary_entries (
            scope,
            COALESCE(user_id, '{_ZERO_UUID}'::uuid),
            COALESCE(tenant_id, '{_ZERO_UUID}'::uuid),
            COALESCE(project_id, '{_ZERO_UUID}'::uuid),
            canonical_term
        )
    """)
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = 'Используй только user_message, evidence и known_facts. Не используй summary агентов как доказательство. Для терминов и аббревиатур возвращай kind=glossary: subject — канонический термин, value — короткое определение, aliases — явно встречающиеся варианты. Turn-level glossary остаётся в tenant scope; company glossary публикуется только source-aware document ingestion. Project glossary не извлекай. Каждый кандидат обязан ссылаться на evidence_source_ids. Не дублируй known_facts и не возвращай больше 8 фактов.',
            updated_at = now()
        WHERE role_type = 'fact_extractor'
    """))


def downgrade() -> None:
    op.drop_index("uq_glossary_entries_identity", table_name="glossary_entries")
    op.create_index(
        "uq_glossary_entries_scope_term", "glossary_entries",
        ["scope", "tenant_id", "project_id", "canonical_term"], unique=True,
    )
