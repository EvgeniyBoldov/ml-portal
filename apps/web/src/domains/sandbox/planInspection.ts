export interface PlanTaskViewModel {
  taskId: string;
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
  revision?: number;
  decision?: string;
  goal?: string;
  rationale?: string;
  trigger?: string;
  tasks: PlanTaskViewModel[];
  removedTasks: string[];
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

export function planDecisionLabel(value: unknown): string | undefined {
  const decision = text(value);
  if (!decision) return undefined;
  return ({ create_plan: 'Сформировать план', revise_plan: 'Перепланировать', ask_user: 'Запросить уточнение', complete_plan: 'Завершить план', fail_plan: 'Остановить план' } as Record<string, string>)[decision] ?? decision;
}

export function taskStatusLabel(value: unknown): string | undefined {
  const status = text(value);
  if (!status) return undefined;
  return ({ pending: 'Ожидает', ready: 'Готова к запуску', running: 'Выполняется', completed: 'Готово', failed: 'Ошибка', unfulfillable: 'Невыполнима', waiting_user: 'Ожидает пользователя', waiting_dependency: 'Ожидает зависимость' } as Record<string, string>)[status] ?? status;
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
  const intent = text(task.intent);
  const objective = text(task.objective ?? task.description ?? task.task_objective);
  const title = text(task.title ?? task.name ?? intent ?? objective ?? taskId) ?? 'Задача без названия';
  return {
    taskId,
    title,
    intent,
    objective,
    instructions: text(task.instructions ?? task.task_instructions),
    executor: text(task.executor ?? task.agent_slug ?? task.assigned_agent),
    status: taskStatusLabel(task.status),
    dependencies: dependencyValues(task.depends_on ?? task.dependencies),
    expectedOutputs: Array.isArray(task.expected_outputs)
      ? task.expected_outputs.map((item) => text(record(item).description ?? record(item).key) ?? '').filter(Boolean)
      : [],
    inputs: task.inputs ?? task.task_inputs,
  };
}

export function projectPlan(value: unknown): PlanViewModel {
  const event = record(value);
  const patch = record(event.patch ?? event.plan ?? event.effective_plan ?? value);
  const taskRecords = Array.isArray(patch.tasks) ? patch.tasks.map(record) : [];
  const taskNames = new Map(taskRecords.map((task) => [text(task.task_id) ?? '', text(task.title) ?? text(task.task_id) ?? 'Задача']));
  const taskById = (id: unknown): string => taskNames.get(String(id)) ?? String(id);
  return {
    revision: typeof event.revision === 'number' ? event.revision : typeof patch.expected_revision === 'number' ? patch.expected_revision + 1 : undefined,
    decision: planDecisionLabel(patch.decision ?? event.decision),
    goal: text(patch.goal ?? event.goal),
    rationale: text(patch.rationale ?? event.rationale),
    trigger: text(patch.trigger ?? event.trigger ?? event.mode),
    tasks: taskRecords.map((task) => {
      const projected = projectPlanTask(task);
      return {
        ...projected,
        dependencies: dependencyValues(task.depends_on ?? task.dependencies, taskNames),
      };
    }),
    removedTasks: Array.isArray(patch.remove_task_ids) ? patch.remove_task_ids.map(taskById) : [],
  };
}
