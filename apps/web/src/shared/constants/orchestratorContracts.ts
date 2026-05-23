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
    goal: { type: 'string', description: 'Цель ответа пользователю' },
    conversation_summary: { type: 'string', description: 'Контекст диалога' },
    agent_results: {
      type: 'array',
      description: 'Результаты ранее вызванных агентов',
      items: {
        type: 'object',
        properties: {
          agent_slug: { type: 'string', description: 'Slug агента' },
          summary: { type: 'string', description: 'Краткий итог результата' },
          success: { type: 'boolean', description: 'Успешность' },
        },
        required: ['agent_slug', 'summary'],
      },
    },
    memory_sections: {
      type: 'array',
      description: 'Выбранные секции памяти',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'Название секции' },
          items_count: { type: 'integer', description: 'Количество элементов в секции' },
        },
        required: ['name'],
      },
    },
    runtime_facts: {
      type: 'array',
      description: 'Собранные факты текущего хода',
      items: { type: 'string' },
    },
    planner_hint: { type: ['string', 'null'], description: 'Подсказка планировщика' },
  },
  required: ['goal', 'agent_results', 'runtime_facts'],
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
