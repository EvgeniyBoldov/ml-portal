import { describe, expect, it } from 'vitest';

import { projectTraceStages } from './traceProjection';
import { replayRuntimeJournal, type RuntimeJournalEvent } from './traceState';

const event = (sequence: number, eventType: string, payload: Record<string, unknown>): RuntimeJournalEvent => ({
  id: `event-${sequence}`,
  run_id: 'run-1',
  sequence,
  event_type: eventType,
  occurred_at: '2026-08-21T08:55:00.000Z',
  entity_type: typeof payload.entity_type === 'string' ? payload.entity_type : null,
  entity_id: typeof payload.entity_id === 'string' ? payload.entity_id : null,
  parent_entity_type: typeof payload.parent_entity_type === 'string' ? payload.parent_entity_type : null,
  parent_entity_id: typeof payload.parent_entity_id === 'string' ? payload.parent_entity_id : null,
  caused_by_event_id: null,
  duration_ms: null,
  payload,
});

describe('projectTraceStages memory components', () => {
  it('projects only persisted fact changes for the fact compactor inspector', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'memory-1', role: 'memory' }),
      event(2, 'agent_start', { entity_type: 'agent_execution', entity_id: 'compactor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1', agent_slug: 'fact_compactor' }),
      event(3, 'memory_component_result', {
        entity_type: 'agent_execution', entity_id: 'compactor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1',
        component_name: 'fact_compactor', status: 'ok', inserted_count: 1, updated_count: 0, skipped_count: 0,
        facts: [{ scope: 'tenant', kind: 'fact', subject: 'network.zone', value: 'production', change_type: 'candidate_confirmed', status_before: 'pending', status_after: 'confirmed', support_before: 2, support_after: 3, support_delta: 1, compaction_action: 'merge' }],
      }),
      event(4, 'agent_end', { entity_type: 'agent_execution', entity_id: 'compactor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1', status: 'completed' }),
    ]);

    const compactor = projectTraceStages(state)[0].executorRuns[0];
    expect(compactor.memoryResult?.facts).toEqual([expect.objectContaining({
      subject: 'network.zone',
      changeType: 'candidate_confirmed',
      statusBefore: 'pending',
      statusAfter: 'confirmed',
      supportDelta: 1,
    })]);
  });
});
