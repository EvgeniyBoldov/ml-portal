import { describe, expect, it } from 'vitest';
import {
  pauseFromJournalEvent,
  reconcileRunStatus,
  shouldApplyJournalPause,
} from './useSandboxRun';

const journal = (event_type: string, payload: Record<string, unknown>) => ({
  id: 'event-1',
  run_id: 'run-1',
  sequence: 1,
  event_type,
  occurred_at: '2026-07-31T19:30:25.000Z',
  entity_type: 'interaction',
  entity_id: 'interaction-1',
  parent_entity_type: 'planner_iteration',
  parent_entity_id: 'iteration-1',
  caused_by_event_id: null,
  duration_ms: null,
  payload,
});

describe('pauseFromJournalEvent', () => {
  it('maps waiting_input journal events to the clarification pause state', () => {
    const pause = pauseFromJournalEvent(
      journal('waiting_input', {
        question: 'Какой файл прочитать?',
        interaction_kind: 'clarify',
      })
    );

    expect(pause).toMatchObject({
      run_id: 'run-1',
      reason: 'waiting_input',
      action: { kind: 'input', question: 'Какой файл прочитать?' },
      context: { question: 'Какой файл прочитать?', contract_version: 1 },
      contract_version: 1,
    });
  });

  it('maps confirmation journal events to the confirmation pause state', () => {
    const pause = pauseFromJournalEvent(
      journal('confirmation_required', {
        context: { summary: 'Подтвердить операцию?', contract_version: 2 },
        action: { operation: 'write', contract_version: 2 },
      })
    );

    expect(pause).toMatchObject({
      run_id: 'run-1',
      reason: 'waiting_confirmation',
      action: { kind: 'confirm', operation: 'write' },
      context: { summary: 'Подтвердить операцию?', contract_version: 2 },
      contract_version: 2,
    });
  });

  it('ignores non-interaction journal events', () => {
    expect(pauseFromJournalEvent(journal('plan_terminal', {}))).toBeNull();
  });

  it('uses a journal pause only until the canonical pause frame arrives', () => {
    expect(shouldApplyJournalPause(false)).toBe(true);
    expect(shouldApplyJournalPause(true)).toBe(false);
  });
});

describe('reconcileRunStatus', () => {
  it('does not regress a terminal SSE status to a stale running snapshot', () => {
    expect(reconcileRunStatus('completed', 'running')).toBe('completed');
    expect(reconcileRunStatus('cancelled', 'running')).toBe('cancelled');
  });

  it('promotes running to a terminal detail status', () => {
    expect(reconcileRunStatus('running', 'completed')).toBe('completed');
    expect(reconcileRunStatus('running', 'failed')).toBe('error');
  });

  it('preserves a pause while detail still reports the run as running', () => {
    expect(reconcileRunStatus('waiting_input', 'running')).toBe(
      'waiting_input'
    );
    expect(reconcileRunStatus('waiting_confirmation', 'running')).toBe(
      'waiting_confirmation'
    );
  });
});
