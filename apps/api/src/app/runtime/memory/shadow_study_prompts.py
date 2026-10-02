"""Fixed prompts for the shadow document-memory study pipeline.

These are the seeded prompts. Operators edit the active prompts from the
"Изучатель документов" orchestration tab; runtime requires a configured prompt.
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

term — внутренний или неоднозначный термин с единым определением:
canonical subject, aliases и content.definition. Определение должно быть явно
подтверждено section; без него term не создавай. Не извлекай общеизвестные
аббревиатуры без особого значения в компании. Для term оставь
scope_candidate=unknown и project_keys/scope_keys пустыми. Не создавай
отдельный description для определения термина. Значения и параметры,
связанные с термином, извлекай как отдельные утверждения памяти.
Создавай term только если document.access_scope=global; локальный документ не
может менять общий словарь.
scope_candidate означает предполагаемую применимость утверждения, а не доступ
к файлу: global, scoped, project или unknown. scope_keys — только те точные ключи
из scope_catalog, для которых sections доказывают применимость именно этого
утверждения. Скоуп, который лишь упомянут, укажи в mentioned_scope_keys.
Если нужное название отсутствует в каталоге, укажи его в unmatched_scope_names;
не придумывай ключ и не создавай скоуп. project_keys оставлены для совместимости.
scope_rationale кратко объясняет основание выбора. *.all относится лишь к своему типу и не означает global.
При сомнении оставь unknown для проверки. Верни только JSON по schema.
Для каждого item content обязателен и должен соответствовать
типизированному формату: rule/constraint/decision содержат statement или
decision, procedure — goal, prechecks, steps, verification и rollback,
description/relationship — summary, term — definition. extraction_confidence — калиброванная
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
    key = DOCUMENT_MEMORY_PROMPT_EXTRA_KEYS[stage]
    configured = extras.get(key) if isinstance(extras, dict) else None
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError(f"Document memory prompt {key} is not configured")
    prompt = configured.strip()
    if stage == "study":
        prompt += "\n\nВ glossary передан весь каталог опубликованных терминов с id, определениями и aliases. Добавляй релевантные ссылки в glossary_term_ids, используя только id из этого каталога. Связь с термином не определяет применимость. scope_catalog содержит все активные области: выбирай доказанные scope_keys, при непустых применимых scope_keys используй scope_candidate=scoped. Для знания, явно относящегося ко всей компании, выбери scope_candidate=global с пустыми scope_keys; *.all относится только к своему типу и не заменяет global. Не оставляй unknown при однозначно доказанной применимости. Поля document scope и access_scope описывают доступ к источнику, а не применимость знания.\n\ncontent_schemas во входном payload задаёт обязательный формат content для каждого candidate_type. Проверяй обязательные поля и допустимые значения по соответствующей схеме. Для rule обязательны statement и effect=require|forbid|allow; definition используется только для term. Для procedure обязательны goal, prechecks, steps (instruction, expected_result, confirmation_required), verification и rollback. Для constraint обязательны statement и limits; для decision — decision; для description/relationship — summary. Не возвращай пустой content и не подставляй definition вместо содержания другого типа. Если источника недостаточно для обязательных полей, пропусти этот item; не придумывай проверки, результат, согласования или откат. subject — читаемое название на языке документа, а не технический slug."
        return prompt + "\n\nОбязательный контракт данных: term содержит название, aliases и content.definition из evidence. Без определения term не создавай. Создавай term только для document.access_scope=global. Не извлекай общеизвестные сокращения без особого значения в компании. Если сам термин называет product, project или team, укажи scope_type. Для других items content обязателен и должен соответствовать типу; scope_keys — только доказанная применимость из scope_catalog; mentioned_scope_keys — простые упоминания. Для применимого неизвестного скоупа создай scope_proposals с type, name, aliases и term_subject. term_subject должен ссылаться на термин этого документа или существующий подтверждённый glossary term; не создавай scope proposal без такого основания. Не придумывай scope key: он назначается runtime при утверждении. Неизвестные области, которые только упомянуты, добавляй в unmatched_scope_names и не превращай в applies_to. scope_catalog содержит все активные области, aliases и при наличии связанный glossary_term; сопоставляй по ключу, названию, aliases и явно связанному термину. Не считай простое упоминание доказательством применимости. При неоднозначном сопоставлении перечисли варианты в unmatched_scope_names и не угадывай. extraction_confidence — калиброванная оценка 0..1; не ставь 1.0 без полного evidence."
    return prompt
