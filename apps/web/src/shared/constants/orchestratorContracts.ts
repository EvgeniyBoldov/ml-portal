export const PLANNER_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    goal: { type: 'string', description: 'Цель runtime run' },
    trigger: { type: 'string', description: 'Причина planner invocation' },
    execution_ledger: { type: 'object', description: 'Полный структурный ledger задач, попыток, needs и resolutions' },
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
    available_artifacts: {
      type: 'array',
      description: 'Доступные runtime-owned attachment metadata и безопасные snippets.',
      items: { type: 'object' },
    },
    memory_context: {
      type: 'array',
      description: 'Отобранная runtime-проекция долговременной памяти.',
      items: { type: 'object' },
    },
    iteration_contract: { type: 'object', description: 'Tasks are agents only; terminal is planner or synthesis.' },
  },
  required: [
    'goal',
    'trigger',
    'execution_ledger',
    'available_agents',
    'available_artifacts',
    'memory_context',
    'iteration_contract',
  ],
};

export const SYNTHESIZER_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    user_question: {
      type: 'string',
      description: 'Неизменяемая исходная цель runtime run.',
    },
    synthesis_brief: {
      type: 'object',
      description: 'Цель и требования финального ответа, заданные terminal=synthesis iteration.',
      properties: {
        user_question: { type: 'string' },
        planned_work: { type: 'string' },
        purpose: { type: 'string' },
        answer_requirements: { type: 'string' },
      },
      required: ['user_question', 'planned_work', 'purpose', 'answer_requirements'],
    },
    completed_task_reports: {
      type: 'array',
      description: 'Все актуальные успешно завершённые agent-задачи final plan; это единственный фактический контекст ответа.',
      items: {
        type: 'object',
        properties: {
          task_id: { type: 'string' },
          intent: { type: 'string' },
          description: { type: 'string' },
          outputs: { type: 'object', description: 'Runtime-owned outputs.' },
        },
        required: ['task_id', 'intent', 'description', 'outputs'],
      },
    },
    plan_outline: {
      type: 'array',
      description: 'Порядок и terminal завершённых итераций без внутренних task payloads.',
      items: { type: 'object' },
    },
    resolution_decisions: {
      type: 'array',
      description: 'Актуальные решения по partial и незавершённым задачам.',
      items: { type: 'object' },
    },
    limitations: {
      type: 'array',
      description: 'Актуальные user-visible ограничения, которые нельзя скрывать.',
      items: { type: 'object' },
    },
    artifacts: {
      type: 'array',
      description: 'Только verified metadata уже созданных файлов; файлы не читаются повторно.',
      items: {
        type: 'object',
        properties: {
          artifact_id: { type: 'string' },
          file_name: { type: 'string' },
          content_type: { type: 'string' },
          size_bytes: { type: ['integer', 'null'] },
        },
        required: ['artifact_id', 'file_name'],
      },
    },
    sources: {
      type: 'array',
      description: 'Разрешённые source metadata для цитирования.',
      items: { type: 'object' },
    },
  },
  required: [
    'user_question',
    'synthesis_brief',
    'plan_outline',
    'resolution_decisions',
    'completed_task_reports',
    'limitations',
    'artifacts',
    'sources',
  ],
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
