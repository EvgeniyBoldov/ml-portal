import { describe, expect, it } from 'vitest';
import { projectPlanHistory } from './planHistory';
import type { RuntimeJournalEvent } from './traceState';

const event = (
  sequence: number,
  event_type: string,
  payload: Record<string, unknown>,
  entityId = 'plan-1'
): RuntimeJournalEvent => ({
  id: `event-${sequence}`,
  run_id: 'run-1',
  sequence,
  event_type,
  occurred_at: '2026-11-07T00:00:00Z',
  entity_type: event_type.startsWith('checkpoint_') ? 'checkpoint' : 'plan',
  entity_id: entityId,
  parent_entity_type: 'planner_iteration',
  parent_entity_id: String(payload.iteration_id ?? ''),
  caused_by_event_id: null,
  duration_ms: null,
  payload,
});
const task = (task_id: string) => ({
  task_id,
  intent: task_id,
  executor: 'agent',
  instructions: task_id,
  depends_on: [],
});

describe('projectPlanHistory', () => {
  it('replays changes and checkpoints without applying a later decision to an earlier stage', () => {
    const first = event(1, 'plan_iteration_applied', {
      iteration_id: 'i1',
      proposal: { tasks: [task('old')], terminal: 'planner' },
    });
    const second = event(6, 'plan_iteration_applied', {
      iteration_id: 'i2',
      proposal: {
        tasks: [task('replacement'), task('new')],
        terminal: 'synthesis',
        resolutions: [
          {
            task_id: 'old',
            action: 'continue_with_tasks',
            replacement_task_ids: ['replacement'],
            reason: 'Нужны новые данные',
          },
        ],
      },
    });
    const third = event(12, 'plan_iteration_applied', {
      iteration_id: 'i3',
      proposal: {
        tasks: [],
        terminal: 'synthesis',
        resolutions: [
          {
            task_id: 'replacement',
            action: 'exclude_from_scope',
            reason: 'Не требуется',
          },
        ],
      },
    });
    const events = [
      first,
      event(
        2,
        'task_planned',
        { plan_id: 'plan-1', task_id: 'old' },
        'old-entity'
      ),
      event(
        3,
        'task_failed',
        { plan_id: 'plan-1', task_id: 'old' },
        'old-entity'
      ),
      event(
        4,
        'checkpoint_planned',
        { plan_id: 'plan-1', iteration_id: 'i1', declared_next: 'synthesis' },
        'cp1'
      ),
      event(
        5,
        'checkpoint_decided',
        {
          plan_id: 'plan-1',
          iteration_id: 'i1',
          declared_next: 'synthesis',
          effective_next: 'planner',
          reason: 'task_failure',
        },
        'cp1'
      ),
      second,
      event(
        7,
        'task_planned',
        { plan_id: 'plan-1', task_id: 'replacement' },
        'new-entity'
      ),
      event(
        8,
        'task_started',
        { plan_id: 'plan-1', task_id: 'replacement' },
        'new-entity'
      ),
      event(
        9,
        'checkpoint_planned',
        { plan_id: 'plan-1', iteration_id: 'i2', declared_next: 'synthesis' },
        'cp2'
      ),
      event(
        11,
        'task_failed',
        { plan_id: 'plan-1', task_id: 'replacement' },
        'new-entity'
      ),
      third,
    ];
    const one = projectPlanHistory(events, first, 1);
    expect(one.full.tasks).toMatchObject([
      { taskId: 'old', change: 'new', status: 'Ошибка' },
    ]);
    expect(
      one.full.entries?.filter(item => item.kind === 'checkpoint')
    ).toMatchObject([
      {
        checkpoint: {
          id: 'cp1',
          declaredNext: 'synthesis',
          effectiveNext: 'planner',
          decided: true,
        },
      },
    ]);
    const two = projectPlanHistory(events, second, 2);
    expect(
      two.delta.entries?.filter(item => item.kind === 'task')
    ).toMatchObject([
      {
        task: {
          taskId: 'old',
          inactive: true,
          change: 'superseded',
          relatedTaskIds: ['replacement'],
        },
      },
      {
        task: {
          taskId: 'replacement',
          change: 'continuation',
          relatedTaskIds: ['old'],
        },
      },
      { task: { taskId: 'new', change: 'new' } },
    ]);
    expect(
      two.full.tasks.find(item => item.taskId === 'replacement')?.change
    ).toBe('continuation');
    expect(
      two.full.entries?.filter(item => item.kind === 'checkpoint')
    ).toHaveLength(2);
    const three = projectPlanHistory(events, third, 3);
    expect(
      three.full.tasks.find(item => item.taskId === 'replacement')
    ).toMatchObject({ change: 'excluded', inactive: true });
  });

  it('marks missing history without inventing the old task and retains explicit replacement links', () => {
    const selected = event(10, 'plan_iteration_applied', {
      iteration_id: 'i2',
      proposal: {
        tasks: [task('next')],
        terminal: 'planner',
        resolutions: [
          {
            task_id: 'missing',
            action: 'continue_with_tasks',
            replacement_task_ids: ['next'],
          },
        ],
      },
    });
    const { full } = projectPlanHistory([selected], selected, 2);
    expect(full.historyIncomplete).toBe(true);
    expect(full.tasks).toMatchObject([
      { taskId: 'next', change: 'continuation', relatedTaskIds: ['missing'] },
    ]);
    expect(full.tasks).toHaveLength(1);
  });

  it('keeps tasks and checkpoints from a different plan out of the selected view', () => {
    const selected = event(2, 'plan_iteration_applied', {
      iteration_id: 'i1',
      proposal: { tasks: [task('our')], terminal: 'planner' },
    });
    const foreign = event(
      1,
      'plan_iteration_applied',
      {
        iteration_id: 'foreign',
        proposal: { tasks: [task('other')], terminal: 'planner' },
      },
      'plan-2'
    );
    expect(
      projectPlanHistory([foreign, selected], selected, 1).full.tasks.map(
        item => item.taskId
      )
    ).toEqual(['our']);
  });
});
