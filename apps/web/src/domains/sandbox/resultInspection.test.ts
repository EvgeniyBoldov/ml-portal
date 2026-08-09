import { describe, expect, it } from 'vitest';
import { projectExecutorResult, resultStatusLabel } from './resultInspection';
import type { TraceExecutorRun } from './traceProjection';
import type { RuntimeJournalEvent, SandboxTraceState, TraceEntity } from './traceState';

const event = (id: string, sequence: number, eventType: string, payload: Record<string, unknown>, parentId?: string): RuntimeJournalEvent => ({
  id, run_id: 'run-1', sequence, event_type: eventType, occurred_at: '2026-08-06T12:00:00Z',
  entity_type: eventType === 'final_answer_marker' ? 'run' : 'synthesis_run', entity_id: eventType === 'final_answer_marker' ? 'run-1' : 'synth-1',
  parent_entity_type: parentId ? 'synthesis_run' : 'run', parent_entity_id: parentId ?? 'run-1', caused_by_event_id: null, duration_ms: null, payload,
});

const synthesisEntity: TraceEntity = {
  key: 'synthesis_run:synth-1', type: 'synthesis_run', id: 'synth-1', parentKey: 'run:run-1', childKeys: [], eventIds: ['start'], status: 'completed', snapshotsByKind: {},
};

const synthesizer: TraceExecutorRun = {
  entity: synthesisEntity, start: event('start', 1, 'synthesis_start', {}), task: 'Подготовка финального ответа',
  executorType: 'SYNTHESIZER', executorName: 'Синтезатор', executorSlug: 'synthesizer', calls: [], metrics: {},
};

describe('result inspection projection', () => {
  it('uses user-facing labels for terminal runtime states', () => {
    expect(resultStatusLabel('completed')).toBe('Готово');
    expect(resultStatusLabel('failed')).toBe('Ошибка');
    expect(resultStatusLabel('unfulfillable')).toBe('Неисполнимо');
    expect(resultStatusLabel('aborted')).toBe('Прервано');
  });

  it('reads synthesizer output from its canonical final answer marker', () => {
    const marker = event('marker', 2, 'final_answer_marker', { content: 'Готовый ответ' }, 'synth-1');
    const trace: SandboxTraceState = {
      runId: 'run-1', rootEntityKey: 'run:run-1', eventsById: { start: synthesizer.start, marker }, eventIdsBySequence: ['start', 'marker'],
      entitiesByKey: { [synthesisEntity.key]: synthesisEntity }, nextSequence: 3, pendingBySequence: {}, protocolError: null,
    };
    expect(projectExecutorResult(synthesizer, trace)).toMatchObject({ status: 'completed', output: 'Готовый ответ' });
  });
});
