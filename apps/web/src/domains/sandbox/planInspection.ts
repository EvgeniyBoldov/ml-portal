export interface PlanTaskViewModel {
  taskId: string;
  kind: 'agent';
  title: string;
  intent?: string;
  objective?: string;
  instructions?: string;
  executor?: string;
  status?: string;
  dependencies: string[];
  expectedOutputs: string[];
  inputs?: unknown;
}

export interface PlanViewModel {
  iteration?: number;
  terminal?: string;
  goal?: string;
  trigger?: string;
  tasks: PlanTaskViewModel[];
}

const record = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value) as unknown;
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
    } catch {
      return {};
    }
  }
  return {};
};

const text = (value: unknown): string | undefined => typeof value === 'string' && value.trim() ? value.trim() : undefined;

export function taskStatusLabel(value: unknown): string | undefined {
  const status = text(value);
  if (!status) return undefined;
  return ({ pending: 'Ожидает', running: 'Выполняется', waiting_retry: 'Ожидает повтора', waiting_confirmation: 'Ожидает подтверждения', needs_dependency: 'Требуются данные', blocked: 'Заблокирована', completed: 'Готово', failed: 'Ошибка', unfulfillable: 'Невыполнима', cancelled: 'Отменена' } as Record<string, string>)[status] ?? status;
}

function dependencyValues(value: unknown, taskNames?: Map<string, string>): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const id = String(item);
    return taskNames?.get(id) ?? id;
  });
}

export function projectPlanTask(value: unknown, fallbackTaskId = 'task'): PlanTaskViewModel {
  const task = record(value);
  const taskId = text(task.task_id ?? task.id) ?? fallbackTaskId;
  const kind = 'agent' as const;
  const intent = text(task.intent);
  const objective = text(task.objective ?? task.description ?? task.task_objective);
  const title = text(task.title ?? task.name ?? intent ?? objective ?? taskId) ?? 'Задача без названия';
  return {
    taskId,
    kind,
    title,
    intent,
    objective,
    instructions: text(task.instructions ?? task.task_instructions),
    executor: text(task.executor ?? task.agent_slug ?? task.assigned_agent),
    status: taskStatusLabel(task.status),
    dependencies: dependencyValues(task.depends_on ?? task.dependencies),
    expectedOutputs: kind === 'agent' && Array.isArray(task.expected_outputs)
      ? task.expected_outputs.map((item) => text(record(item).description ?? record(item).key) ?? '').filter(Boolean)
      : [],
    inputs: kind === 'agent' ? task.inputs ?? task.task_inputs : undefined,
  };
}

export function projectPlan(value: unknown): PlanViewModel {
  const event = record(value);
  const proposal = record(event.proposal ?? event);
  const taskRecords = Array.isArray(proposal.tasks) ? proposal.tasks.map(record) : [];
  const taskNames = new Map(taskRecords.map((task) => [text(task.task_id) ?? '', text(task.title) ?? text(task.task_id) ?? 'Задача']));
  return {
    iteration: typeof event.sequence === 'number' ? event.sequence : typeof event.iteration === 'number' ? event.iteration : undefined,
    terminal: text(proposal.terminal ?? event.terminal),
    goal: text(event.goal),
    trigger: text(event.trigger),
    tasks: taskRecords.map((task) => {
      const projected = projectPlanTask(task);
      return {
        ...projected,
        dependencies: dependencyValues(task.depends_on ?? task.dependencies, taskNames),
      };
    }),
  };
}
