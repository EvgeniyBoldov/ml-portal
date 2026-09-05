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
    terminal_synthesis: {
      type: 'object',
      description: 'Встроенный terminal node без executor. Planner обязан включить ровно один kind=synthesis в итоговый граф.',
      properties: {
        kind: { const: 'synthesis' },
        executor: { type: 'null' },
        purpose: { type: 'string' },
      },
      required: ['kind', 'executor', 'purpose'],
    },
  },
  required: ['goal', 'trigger', 'plan', 'completed_outputs', 'needs', 'last_failure', 'available_agents', 'terminal_synthesis'],
};

export const SYNTHESIZER_INPUT_CONTRACT = {
  type: 'object',
  properties: {
    synthesis_task: {
      type: 'object',
      description: 'Терминальная задача планировщика: какой смысл вопроса пользователя и в каком направлении отвечать.',
      properties: {
        task_id: { type: 'string' },
        intent: { type: 'string' },
        instructions: { type: 'string' },
      },
      required: ['task_id', 'intent', 'instructions'],
    },
    completed_task_reports: {
      type: 'array',
      description: 'Все актуальные успешно завершённые agent-задачи final plan; это единственный фактический контекст ответа.',
      items: {
        type: 'object',
        properties: {
          task_id: { type: 'string' },
          intent: { type: 'string' },
          instructions: { type: 'string' },
          report: { type: 'object', description: 'Канонический отчёт агента: description и outputs.' },
        },
        required: ['task_id', 'intent', 'instructions', 'report'],
      },
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
  required: ['synthesis_task', 'completed_task_reports', 'artifacts', 'sources'],
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
