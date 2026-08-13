export const PLANNER_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    goal: { type: 'string', description: 'Текущая цель текущего плана' },
    trigger: { type: ['string', 'null'], description: 'Причина вызова planner: initial или причина репланирования' },
    plan: {
      type: 'object',
      description: 'Текущее сохранённое состояние графа: revision, tasks, outputs и статусы',
      properties: {
        revision: { type: 'integer', description: 'Версия плана, обязательная для expected_revision' },
        tasks: { type: 'object', description: 'Задачи текущего графа' },
        outputs: { type: 'object', description: 'Результаты задач текущего графа' },
      },
      required: ['revision', 'tasks', 'outputs'],
    },
    completed_outputs: { type: 'object', description: 'Новые завершённые результаты для решения planner' },
    needs: { type: 'array', description: 'Незакрытые потребности задач' },
    last_failure: { type: ['object', 'null'], description: 'Последняя техническая или агентская ошибка' },
    available_agents: {
      type: 'array',
      description: 'Доступные агенты для вызова',
      items: {
        type: 'object',
        properties: {
          slug: { type: 'string', description: 'Slug агента' },
          description: { type: 'string', description: 'Короткое описание агента' },
        },
        required: ['slug'],
      },
    },
  },
  required: ['goal', 'trigger', 'plan', 'completed_outputs', 'needs', 'last_failure', 'available_agents'],
};

export const SYNTHESIZER_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    answer_brief: {
      type: 'string',
      description: 'Канонический черновик ответа пользователю. Synthesizer редактирует форму, но не меняет смысл.',
    },
    generated_files: {
      type: 'array',
      description: 'Файлы, которые нужно явно упомянуть или отдать ссылкой пользователю',
      items: {
        type: 'object',
        properties: {
          artifact_id: { type: 'string', description: 'Непрозрачный идентификатор артефакта' },
          file_name: { type: 'string', description: 'Имя файла для показа в ответе' },
          download_url: { type: 'string', description: 'Ссылка на скачивание файла' },
          content_type: { type: 'string', description: 'MIME-тип файла' },
          size_bytes: { type: ['integer', 'null'], description: 'Размер файла в байтах' },
        },
        required: ['artifact_id', 'file_name'],
      },
    },
    rag_sources: {
      type: 'array',
      description: 'Структурированные источники из RAG/документного поиска для цитирования',
      items: {
        type: 'object',
        properties: {
          source_id: { type: 'string', description: 'Идентификатор источника' },
          source_name: { type: 'string', description: 'Отображаемое имя документа/источника' },
          text: { type: 'string', description: 'Короткий фрагмент или snippet' },
          page: { type: ['integer', 'null'], description: 'Номер страницы, если известен' },
          score: { type: ['number', 'null'], description: 'Оценка релевантности' },
        },
      },
    },
    language_hint: {
      type: ['string', 'null'],
      description: 'Подсказка по языку итогового ответа',
    },
    style_constraints: {
      type: ['object', 'null'],
      description: 'Ограничения на форму итогового текста',
      properties: {
        concise: { type: 'boolean', description: 'Сделать ответ компактным' },
        preserve_lists: { type: 'boolean', description: 'Сохранять списки из answer_brief' },
        preserve_order: { type: 'boolean', description: 'Сохранять порядок тезисов из answer_brief' },
      },
    },
  },
  required: ['answer_brief', 'generated_files', 'rag_sources'],
};

export const FACT_EXTRACTOR_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    user_message: { type: 'string', description: 'Текущее сообщение пользователя' },
    evidence: {
      type: 'array',
      description: 'Первичные источники: сообщение пользователя или результат инструмента',
      items: {
        type: 'object',
        properties: {
          source_id: { type: 'string', description: 'Идентификатор первичного источника' },
          source_type: { type: 'string', description: 'user_message или tool_result' },
          source_ref: { type: 'string', description: 'Ссылка на источник в runtime' },
          text: { type: 'string', description: 'Текст доказательства' },
        },
        required: ['source_id', 'source_type', 'source_ref', 'text'],
      },
    },
    known_facts: {
      type: 'array',
      description: 'Известные уже факты для дедупликации',
      items: {
        type: 'object',
        properties: {
          subject: { type: 'string', description: 'Ключ факта' },
          value: { type: 'string', description: 'Значение факта' },
        },
        required: ['subject', 'value'],
      },
    },
  },
  required: ['user_message', 'evidence', 'known_facts'],
};

export const MEMORY_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    request: { type: 'string', description: 'Текущий запрос пользователя' },
    facts: {
      type: 'array',
      description: 'Долговременные факты с индексами для отбора',
      items: { type: 'object' },
    },
    projects: {
      type: 'array',
      description: 'Проекты и aliases с индексами для отбора',
      items: { type: 'object' },
    },
  },
  required: ['request', 'facts', 'projects'],
};

export const FACT_COMPACTOR_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    candidates: { type: 'array', description: 'Новые кандидаты фактов с индексами' },
    current_facts: { type: 'array', description: 'Текущие подтверждённые факты' },
  },
  required: ['candidates', 'current_facts'],
};
