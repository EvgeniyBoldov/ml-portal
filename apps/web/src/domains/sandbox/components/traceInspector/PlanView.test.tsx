import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HumanPlanView } from './PlanView';
import type { PlanTaskViewModel } from '../../planInspection';

const task = (
  taskId: string,
  values: Partial<PlanTaskViewModel> = {}
): PlanTaskViewModel => ({
  taskId,
  kind: 'agent',
  title: taskId,
  dependencies: [],
  expectedOutputs: [],
  ...values,
});

describe('HumanPlanView', () => {
  it('renders the old task, linked continuation and checkpoint with text labels', () => {
    render(
      <HumanPlanView
        plan={{
          tasks: [],
          entries: [
            {
              kind: 'task',
              task: task('old', {
                inactive: true,
                change: 'superseded',
                relatedTaskIds: ['new'],
              }),
            },
            {
              kind: 'task',
              task: task('new', {
                change: 'continuation',
                relatedTaskIds: ['old'],
              }),
            },
            { kind: 'task', task: task('fresh', { change: 'new' }) },
            {
              kind: 'checkpoint',
              checkpoint: {
                id: 'c1',
                iteration: 1,
                declaredNext: 'synthesis',
                effectiveNext: 'planner',
                reason: 'task_failure',
                decided: true,
              },
            },
          ],
        }}
      />
    );
    expect(screen.getByText('Продолжена новой задачей')).toBeInTheDocument();
    expect(screen.getByText('Продолжена новой задачей').closest('article')?.className).toContain('inactive');
    expect(screen.getByText('Продолжение').closest('article')?.className).toContain('continuation');
    expect(screen.getByText('Новая').closest('article')?.className).toContain('new');
    expect(screen.getByText('Продолжает: old')).toBeInTheDocument();
    expect(screen.getByText('Продолжение: new')).toBeInTheDocument();
    expect(
      screen.getByText('Запланировано: Синтез ответа')
    ).toBeInTheDocument();
    expect(screen.getByText('Решение: Планировщик')).toBeInTheDocument();
  });

  it('explicitly reports incomplete history', () => {
    render(
      <HumanPlanView
        plan={{ tasks: [], entries: [], historyIncomplete: true }}
      />
    );
    expect(screen.getByText(/История плана неполная/)).toBeInTheDocument();
  });
});
