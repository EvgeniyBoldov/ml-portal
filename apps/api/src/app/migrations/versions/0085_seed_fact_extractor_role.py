"""Ensure the fact extractor has a database-backed default prompt."""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Seed only a missing mandatory system role; never overwrite admin edits."""
    op.get_bind().execute(sa.text("""
        INSERT INTO system_llm_roles (
            id, role_type, identity, mission, rules, safety, output_requirements,
            model, temperature, max_tokens, timeout_s, max_retries, retry_backoff,
            is_active, created_at, updated_at
        )
        SELECT :id, 'fact_extractor', :identity, :mission, :rules, :safety, :output_requirements,
               :model, 0.1, 800, 15, 1, 'none', true, now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM system_llm_roles
            WHERE role_type = 'fact_extractor' AND COALESCE(is_active, true) = true
        )
    """), {
        "id": uuid.uuid5(uuid.NAMESPACE_URL, "ml-portal/system-role/fact-extractor"),
        "identity": "Ты — экстрактор фактов для корпоративного AI-портала.",
        "mission": "Извлеки атомарные устойчивые факты только из сообщения пользователя и первичных успешных результатов tools.",
        "rules": "Вход: user_message, evidence, known_facts. Верни JSON {facts:[{scope, project_key, subject, value, confidence, evidence_source_ids}]}. Каждый факт обязан ссылаться на evidence_source_ids; выводы агентов, планера и synthesizer не являются источниками.",
        "safety": "Не извлекай секреты, токены, пароли и сведения без первичного evidence.",
        "output_requirements": "Чистый JSON без пояснений и markdown.",
        "model": "llm.llama4.scout",
    })


def downgrade() -> None:
    # Existing role may have been edited after seed; do not delete it.
    pass
