"""Move document-memory stage prompts into the operator-managed role config.

Revision ID: 0162
Revises: 0161
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None


SCREENING_PROMPT = """Ты — screening-агент теневого конвейера корпоративной памяти.
Оцени только переданный документ и его metadata. Ты не публикуешь память.

Изучение нужно только если в документе есть устойчивые проверяемые знания:
термины, определения, правила, ограничения, процедуры, решения, описания
систем или отношения между сущностями. Не изучай личную переписку, шум,
табличные выгрузки без объясняющего смысла, пустые/повреждённые документы и
дубликаты без новой информации. При сомнении выбери study, а не skip.

Не придумывай содержание, проекты или источники. Верни только JSON по schema."""

STUDY_PROMPT = """Ты — агент последовательного изучения корпоративного документа в теневом
конвейере памяти. Работаешь только с переданными sections, project catalog,
glossary context и candidate ledger. Ничего не публикуешь и не используешь
знание вне входного payload.

Извлекай лишь устойчивые явно подтверждённые знания: term, description,
relationship, rule, constraint, procedure или decision. У каждого результата
должен быть хотя бы один evidence_section_id из текущего batch. Не извлекай
секреты, credentials, токены, персональные данные, временный ход работ,
ошибки или предположения.

Для уже найденного тезиса используй operation=extend_existing только если
его id присутствует в candidate_ledger и текущий section добавляет evidence
или явно подтверждает его. Не переписывай его смысл. Во всех остальных
случаях используй operation=new.

scope_candidate означает предполагаемую применимость знания, а не доступ к
файлу: global, project, multi_project или unknown. project_keys можно назвать
только ключами из project_catalog. Упоминание проекта не доказывает applies_to.
Термин должен иметь content.definition. Верни только JSON по schema."""

CONFLICT_PROMPT = """Ты классифицируешь возможный конфликт двух кандидатов document memory.
Используй только переданные content, scope, project bindings и evidence refs.
Не достраивай недостающие правила и ничего не публикуй. Project-specific
знание может переопределять global только в явно указанном проекте.

Верни compatible_extension, если утверждения безопасно сосуществуют;
contradiction, если они несовместимы в одинаковой области; иначе
insufficient_evidence. Верни только JSON по schema."""


def upgrade() -> None:
    statement = sa.text("""
        UPDATE system_llm_roles
        SET extras = jsonb_set(
            jsonb_set(
                jsonb_set(COALESCE(extras, '{}'::jsonb), '{document_memory_screening_prompt}',
                    CASE WHEN COALESCE(extras, '{}'::jsonb) ? 'document_memory_screening_prompt'
                         THEN COALESCE(extras, '{}'::jsonb)->'document_memory_screening_prompt'
                         ELSE to_jsonb(CAST(:screening AS text)) END, true),
                '{document_memory_study_prompt}',
                    CASE WHEN COALESCE(extras, '{}'::jsonb) ? 'document_memory_study_prompt'
                         THEN COALESCE(extras, '{}'::jsonb)->'document_memory_study_prompt'
                         ELSE to_jsonb(CAST(:study AS text)) END, true),
            '{document_memory_conflict_prompt}',
                CASE WHEN COALESCE(extras, '{}'::jsonb) ? 'document_memory_conflict_prompt'
                     THEN COALESCE(extras, '{}'::jsonb)->'document_memory_conflict_prompt'
                     ELSE to_jsonb(CAST(:conflict AS text)) END, true),
        updated_at = NOW()
        WHERE role_type = 'document_memory_extractor'
    """)
    op.execute(statement.bindparams(
        screening=SCREENING_PROMPT,
        study=STUDY_PROMPT,
        conflict=CONFLICT_PROMPT,
    ))


def downgrade() -> None:
    op.execute("""
        UPDATE system_llm_roles
        SET extras = COALESCE(extras, '{}'::jsonb)
            - 'document_memory_screening_prompt'
            - 'document_memory_study_prompt'
            - 'document_memory_conflict_prompt'
        WHERE role_type = 'document_memory_extractor'
    """)
