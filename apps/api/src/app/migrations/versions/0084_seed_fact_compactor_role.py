"""Seed the mandatory fact compactor system role."""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        INSERT INTO system_llm_roles (
            id, role_type, identity, mission, rules, safety, output_requirements,
            model, temperature, max_tokens, timeout_s, max_retries, retry_backoff,
            is_active, created_at, updated_at
        )
        SELECT :id, 'fact_compactor', :identity, :mission, :rules, :safety, :output_requirements,
               :model, 0.0, 800, 15, 1, 'none', true, now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM system_llm_roles
            WHERE role_type = 'fact_compactor' AND COALESCE(is_active, true) = true
        )
    """), {
        "id": uuid.uuid5(uuid.NAMESPACE_URL, "ml-portal/system-role/fact-compactor"),
        "identity": "Ты — компактор подтверждаемых фактов корпоративного AI-портала.",
        "mission": "Объедини новые факты с текущими фактами того же субъекта, не придумывая новых сведений.",
        "rules": "Верни только нормализованные факты из candidates. Объединяй смысловые дубли; не выбирай значение при противоречии и не создавай факт без source_candidate_indexes.",
        "safety": "Не добавляй сведения, которых нет в candidates.",
        "output_requirements": "Чистый JSON без пояснений и markdown.",
        "model": "llm.llama4.scout",
    })


def downgrade() -> None:
    # System roles may be edited after seed; downgrade must not delete them.
    pass
