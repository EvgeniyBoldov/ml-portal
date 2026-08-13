"""Normalize database-backed roles to the active runtime surface.

Revision ID: 0087
Revises: 0086
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


MEMORY_DEFAULT = {
    "identity": "Ты — подготовитель памяти для планера корпоративного AI-портала.",
    "mission": "Отбери проверяемый контекст из долговременной памяти и глоссария проектов для текущего запроса.",
    "rules": "Используй только индексы facts и projects из входного JSON. Не добавляй факты и не строй план. Выбирай не более 12 фактов и 3 проектов; при отсутствии совпадений верни пустые массивы.",
    "safety": "Не выбирай и не раскрывай секреты, токены, пароли или чувствительные данные.",
    "output_requirements": "Верни JSON с fact_indexes, project_indexes и ambiguities. Каждый индекс обязан существовать во входе.",
    "model": "llm.llama4.scout",
    "temperature": 0.1,
    "max_tokens": 400,
    "timeout_s": 20,
    "max_retries": 1,
    "retry_backoff": "none",
}

FACT_EXTRACTOR_DEFAULT = {
    "identity": "Ты — экстрактор устойчивых фактов корпоративного AI-портала.",
    "mission": "Извлеки атомарные факты только из сообщения пользователя и первичного evidence для будущих обращений.",
    "rules": "Вход: user_message, evidence, known_facts. Не используй summary агентов как доказательство. Возвращай только подтверждённые user, tenant или project факты с evidence_source_ids; не дублируй known_facts и не возвращай более 8 фактов.",
    "safety": "Не извлекай секреты, токены, пароли и чувствительные персональные данные.",
    "output_requirements": "Верни JSON с facts[]. Каждый факт содержит scope, subject, value, confidence, project_key, project_aliases и evidence_source_ids.",
    "model": "llm.llama4.scout",
    "temperature": 0.1,
    "max_tokens": 800,
    "timeout_s": 15,
    "max_retries": 1,
    "retry_backoff": "none",
}

FACT_COMPACTOR_DEFAULT = {
    "identity": "Ты — компактор подтверждаемых фактов корпоративного AI-портала.",
    "mission": "Нормализуй кандидаты фактов без создания новых сведений.",
    "rules": "Используй только candidates. Объединяй смысловые дубли, не разрешай противоречия и всегда указывай source_candidate_indexes.",
    "safety": "Не добавляй сведения, которых нет в candidates.",
    "output_requirements": "Верни JSON с facts[]. Каждый факт содержит scope, subject, value и source_candidate_indexes.",
    "model": "llm.llama4.scout",
    "temperature": 0.0,
    "max_tokens": 800,
    "timeout_s": 15,
    "max_retries": 1,
    "retry_backoff": "none",
}


def _insert_missing(conn, role_type: str, prompt: dict[str, object]) -> None:
    conn.execute(sa.text("""
        INSERT INTO system_llm_roles (
            id, role_type, identity, mission, rules, safety, output_requirements,
            model, temperature, max_tokens, timeout_s, max_retries, retry_backoff,
            is_active, created_at, updated_at
        )
        SELECT :id, :insert_role_type, :identity, :mission, :rules, :safety, :output_requirements,
               :model, :temperature, :max_tokens, :timeout_s, :max_retries, :retry_backoff,
               true, now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM system_llm_roles
            WHERE role_type = :lookup_role_type AND COALESCE(is_active, true) = true
        )
    """), {
        **prompt,
        "id": uuid.uuid5(uuid.NAMESPACE_URL, f"ml-portal/system-role/{role_type}"),
        # PostgreSQL may infer a single reused bind parameter as both text
        # and varchar in the INSERT ... SELECT / NOT EXISTS expression.
        # Keep the two contexts independent so the migration is portable
        # across psycopg versions and existing column definitions.
        "insert_role_type": role_type,
        "lookup_role_type": role_type,
    })


def _replace_deprecated_contract(conn, role_type: str, prompt: dict[str, object], legacy_condition: str) -> None:
    conn.execute(sa.text(f"""
        UPDATE system_llm_roles SET
            identity = :identity, mission = :mission, rules = :rules, safety = :safety,
            output_requirements = :output_requirements, model = :model,
            temperature = :temperature, max_tokens = :max_tokens, timeout_s = :timeout_s,
            max_retries = :max_retries, retry_backoff = :retry_backoff, examples = NULL,
            updated_at = now()
        WHERE role_type = :role_type
          AND COALESCE(is_active, true) = true
          AND ({legacy_condition})
    """), {**prompt, "role_type": role_type})


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM system_llm_roles WHERE role_type IN ('triage', 'summary', 'summary_compactor')"))
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('planner', 'memory', 'synthesizer', 'fact_extractor', 'fact_compactor')",
    )
    for role_type, prompt in (
        ("memory", MEMORY_DEFAULT),
        ("fact_extractor", FACT_EXTRACTOR_DEFAULT),
        ("fact_compactor", FACT_COMPACTOR_DEFAULT),
    ):
        _insert_missing(conn, role_type, prompt)
    # Only migrate rows that still carry a deprecated runtime contract. This
    # deliberately leaves independently edited admin prompts untouched.
    _replace_deprecated_contract(
        conn,
        "memory",
        MEMORY_DEFAULT,
        "output_requirements LIKE '%facts, open_questions, risks, next_actions%'",
    )
    _replace_deprecated_contract(
        conn,
        "fact_extractor",
        FACT_EXTRACTOR_DEFAULT,
        "rules LIKE '%agent_results%' OR identity LIKE 'Ты — fact extractor runtime v3%'",
    )


def downgrade() -> None:
    # Legacy roles are intentionally not restored.
    pass
