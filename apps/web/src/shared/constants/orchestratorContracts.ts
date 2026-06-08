export const PLANNER_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    goal: { type: 'string', description: 'Текущая цель текущего плана' },
    conversation_summary: { type: 'string', description: 'Сжатый контекст диалога' },
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
    execution_outline: {
      type: ['object', 'null'],
      description: 'Рекомендуемый план/фазы выполнения',
    },
    memory: {
      type: 'object',
      description: 'Снимок планировочного состояния и памяти',
    },
    policies: { type: 'string', description: 'Текст платформенных политик' },
  },
  required: ['goal', 'available_agents', 'memory', 'policies'],
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
          file_id: { type: 'string', description: 'Стабильный идентификатор файла' },
          file_name: { type: 'string', description: 'Имя файла для показа в ответе' },
          download_url: { type: 'string', description: 'Ссылка на скачивание файла' },
          content_type: { type: 'string', description: 'MIME-тип файла' },
          size_bytes: { type: ['integer', 'null'], description: 'Размер файла в байтах' },
        },
        required: ['file_id', 'file_name'],
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
    agent_results: {
      type: 'array',
      description: 'Итоги агентских вызовов',
      items: {
        type: 'object',
        properties: {
          agent: { type: 'string', description: 'Название агента' },
          summary: { type: 'string', description: 'Краткий итог' },
          success: { type: 'boolean', description: 'Успешность' },
        },
        required: ['agent', 'summary'],
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
  required: ['user_message', 'agent_results', 'known_facts'],
};

export const SUMMARY_COMPACTOR_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    previous: {
      type: 'object',
      description: 'Предыдущий summary-снимок',
    },
    turn_delta: {
      type: 'object',
      description: 'Изменения текущего хода',
    },
    turn_number: { type: 'integer', description: 'Номер хода' },
  },
  required: ['previous', 'turn_delta', 'turn_number'],
};
