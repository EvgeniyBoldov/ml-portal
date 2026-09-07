import { describe, expect, it } from 'vitest';
import { projectPlan, projectPlanTask } from './planInspection';

describe('plan inspection projection', () => {
  it('projects an immutable iteration into stable task cards', () => {
    expect(projectPlan({ iteration: 2, terminal: 'planner', trigger: 'task_failure', proposal: {
      tasks: [
        { task_id: 'discover', title: 'Найти шаблон', objective: 'Выбрать готовый шаблон', agent_slug: 'viewer', status: 'completed' },
        { task_id: 'fill', title: 'Заполнить шаблон', objective: 'Создать файл', agent_slug: 'net.enginer', depends_on: ['discover'], expected_outputs: [{ key: 'artifact', description: 'Готовый файл' }] },
      ], terminal: 'planner',
    } })).toEqual({
      iteration: 2,
      terminal: 'planner',
      goal: undefined,
      trigger: 'task_failure',
      tasks: [
        { taskId: 'discover', kind: 'agent', title: 'Найти шаблон', intent: undefined, objective: 'Выбрать готовый шаблон', instructions: undefined, executor: 'viewer', status: 'Готово', dependencies: [], expectedOutputs: [], inputs: undefined },
        { taskId: 'fill', kind: 'agent', title: 'Заполнить шаблон', intent: undefined, objective: 'Создать файл', instructions: undefined, executor: 'net.enginer', status: undefined, dependencies: ['Найти шаблон'], expectedOutputs: ['Готовый файл'], inputs: undefined },
      ],
    });
  });

  it('normalizes one agent task into the same model as a plan item', () => {
    expect(projectPlanTask({
      task_id: 'fill',
      intent: 'fill_template',
      instructions: 'Заполнить выбранный шаблон',
      executor: 'net.enginer',
      task_inputs: { row_id: 'template-1' },
    })).toEqual({
      taskId: 'fill', kind: 'agent',
      title: 'fill_template',
      intent: 'fill_template',
      objective: undefined,
      instructions: 'Заполнить выбранный шаблон',
      executor: 'net.enginer',
      status: undefined,
      dependencies: [],
      expectedOutputs: [],
      inputs: { row_id: 'template-1' },
    });
  });

});
