import { describe, expect, it } from 'vitest';
import { projectPlan } from './planInspection';

describe('plan inspection projection', () => {
  it('projects planner patch into task cards without exposing task ids', () => {
    expect(projectPlan({ revision: 2, patch: {
      decision: 'revise_plan', goal: 'Подготовить заявку', rationale: 'Первая попытка не удалась',
      tasks: [
        { task_id: 'discover', title: 'Найти шаблон', objective: 'Выбрать готовый шаблон', agent_slug: 'viewer', status: 'completed' },
        { task_id: 'fill', title: 'Заполнить шаблон', objective: 'Создать файл', agent_slug: 'net.enginer', depends_on: ['discover'], expected_outputs: [{ key: 'artifact', description: 'Готовый файл' }] },
      ],
      remove_task_ids: ['obsolete'],
    } })).toEqual({
      revision: 2,
      decision: 'Перепланировать',
      goal: 'Подготовить заявку',
      rationale: 'Первая попытка не удалась',
      trigger: undefined,
      tasks: [
        { title: 'Найти шаблон', objective: 'Выбрать готовый шаблон', executor: 'viewer', status: 'Готово', dependencies: [], expectedOutputs: [], inputs: undefined },
        { title: 'Заполнить шаблон', objective: 'Создать файл', executor: 'net.enginer', status: undefined, dependencies: ['Найти шаблон'], expectedOutputs: ['Готовый файл'], inputs: undefined },
      ],
      removedTasks: ['obsolete'],
    });
  });
});
