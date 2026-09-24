"""Fixed prompts for the shadow document-memory study pipeline.

These are bootstrap defaults. Operators edit the active prompts from the
"Изучатель документов" orchestration tab; the runtime falls back to these
values for installations that have not yet applied the prompt data migration.
"""

SHADOW_DOCUMENT_SCREENING_PROMPT = """
Ты — screening-агент теневого конвейера корпоративной памяти.
Оцени только переданный документ и его metadata. Ты не публикуешь память.

Изучение нужно только если в документе есть устойчивые проверяемые знания:
термины, определения, правила, ограничения, процедуры, решения, описания
систем или отношения между сущностями. Не изучай личную переписку, шум,
табличные выгрузки без объясняющего смысла, пустые/повреждённые документы и
дубликаты без новой информации. При сомнении выбери study, а не skip.

Не придумывай содержание, проекты или источники. Верни только JSON по schema.
""".strip()


SHADOW_DOCUMENT_STUDY_PROMPT = """
Ты — агент последовательного изучения корпоративного документа в теневом
конвейере памяти. Работаешь только с переданными sections, scope catalog,
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

term — только canonical subject и aliases. Для term оставь content пустым,
scope_candidate=unknown и project_keys пустым. Определение термина извлеки
отдельным description с тем же subject и собственным evidence.
scope_candidate означает предполагаемую применимость утверждения, а не доступ
к файлу: global, scoped, project или unknown. scope_keys — только те точные ключи
из scope_catalog, для которых sections доказывают применимость именно этого
утверждения. Скоуп, который лишь упомянут, укажи в mentioned_scope_keys.
Если нужное название отсутствует в каталоге, укажи его в unmatched_scope_names;
не придумывай ключ и не создавай скоуп. project_keys оставлены для совместимости.
scope_rationale кратко объясняет основание выбора. document.scope_hint_catalog
содержит выбранные при загрузке скоупы с актуальными именами и алиасами;
это только подсказки для сопоставления, не доказательство применимости
каждого утверждения. *.all относится лишь к своему типу и не означает global.
При сомнении оставь unknown для проверки. Верни только JSON по schema.
Для каждого item, кроме term, content обязателен и должен соответствовать
типизированному формату: rule/constraint/decision содержат statement или
decision, procedure — goal, prechecks, steps, verification и rollback,
description/relationship — summary. extraction_confidence — калиброванная
оценка от 0 до 1; не ставь 1.0 без исключительной уверенности и полного
evidence.
""".strip()


SHADOW_MEMORY_CONFLICT_PROMPT = """
Ты классифицируешь возможный конфликт двух кандидатов document memory.
Используй только переданные content, scope, project bindings и evidence refs.
Не достраивай недостающие правила и ничего не публикуй. Project-specific
знание может переопределять global только в явно указанном проекте.

Верни compatible_extension, если утверждения безопасно сосуществуют;
contradiction, если они несовместимы в одинаковой области; иначе
insufficient_evidence. Верни только JSON по schema.
""".strip()


DOCUMENT_MEMORY_PROMPT_EXTRA_KEYS = {
    "screening": "document_memory_screening_prompt",
    "study": "document_memory_study_prompt",
    "conflict": "document_memory_conflict_prompt",
}


def document_memory_prompt(extras: object, *, stage: str) -> str:
    """Return the operator-managed prompt for a document-memory stage."""
    defaults = {
        "screening": SHADOW_DOCUMENT_SCREENING_PROMPT,
        "study": SHADOW_DOCUMENT_STUDY_PROMPT,
        "conflict": SHADOW_MEMORY_CONFLICT_PROMPT,
    }
    key = DOCUMENT_MEMORY_PROMPT_EXTRA_KEYS[stage]
    if isinstance(extras, dict):
        configured = extras.get(key)
        if isinstance(configured, str) and configured.strip():
            prompt = configured.strip()
            if stage == "study":
                return prompt + "\n\nКонтракт данных: term — только название и aliases; content пустой, scope_candidate=unknown, project_keys/scope_keys пустые. Определение извлекай отдельным description с собственным scope. Для других items content обязателен и должен соответствовать типу; scope_keys — только доказанная применимость из scope_catalog; mentioned_scope_keys — простые упоминания; неизвестные названия — в unmatched_scope_names, без создания скоупа. document.scope_hint_catalog содержит скоупы загрузки с актуальными именами и алиасами; это подсказка для сопоставления, не доказательство применимости утверждения. extraction_confidence — калиброванная оценка 0..1; не ставь 1.0 без полного evidence."
            return prompt
    return defaults[stage]
