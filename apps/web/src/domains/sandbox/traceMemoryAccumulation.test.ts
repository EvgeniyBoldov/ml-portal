import { describe, expect, it } from 'vitest';

import {
  memoryContextFromPayload,
  memoryContextFromTool,
  projectTraceStages,
} from './traceProjection';
import { replayRuntimeJournal, type RuntimeJournalEvent } from './traceState';

function event(
  sequence: number,
  eventType: string,
  payload: Record<string, unknown>
): RuntimeJournalEvent {
  return {
    id: `memory-event-${sequence}`,
    run_id: 'run',
    sequence,
    event_type: eventType,
    occurred_at: '2026-10-18T00:00:00Z',
    entity_type: String(payload.entity_type ?? ''),
    entity_id: String(payload.entity_id ?? ''),
    parent_entity_type: payload.parent_entity_type
      ? String(payload.parent_entity_type)
      : null,
    parent_entity_id: payload.parent_entity_id
      ? String(payload.parent_entity_id)
      : null,
    caused_by_event_id: null,
    duration_ms: null,
    payload,
  };
}

const group = (scope: string, text: string) => ({
  scope_slug: scope,
  status: 'completed',
  success: true,
  count: 1,
  items: [
    {
      scope_slug: scope,
      text,
      subject: 'Policy',
      source_references: [{ document_id: scope }],
    },
  ],
});

describe('owner-local accumulated memory', () => {
  it('uses the recorded owner snapshot and keeps the original tool search separate', () => {
    const original = group('company', 'Original passage');
    const accumulated = {
      ...original,
      count: 2,
      items: [
        ...original.items,
        { ...original.items[0], text: 'Second passage' },
      ],
    };
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', {
        entity_type: 'orchestrator',
        entity_id: 'planner',
        role: 'planner',
      }),
      event(2, 'planner_iteration_start', {
        entity_type: 'planner_iteration',
        entity_id: 'iteration',
        parent_entity_type: 'orchestrator',
        parent_entity_id: 'planner',
        iteration: 1,
      }),
      event(3, 'tool_call', {
        entity_type: 'tool_call',
        entity_id: 'search',
        parent_entity_type: 'planner_iteration',
        parent_entity_id: 'iteration',
        tool: 'memory.search',
        call_id: 'search',
      }),
      event(4, 'tool_result', {
        entity_type: 'tool_call',
        entity_id: 'search',
        parent_entity_type: 'planner_iteration',
        parent_entity_id: 'iteration',
        tool: 'memory.search',
        call_id: 'search',
        success: true,
        data: { backend: 'hipporag', groups: [original] },
      }),
      event(5, 'status', {
        entity_type: 'planner_iteration',
        entity_id: 'iteration',
        stage: 'memory_context_used',
        memory_owner: 'planner',
        memory_owner_id: 'plan',
        memory_context: [
          {
            type: 'document_memory',
            groups: [accumulated, group('project', 'Project passage')],
          },
        ],
      }),
    ]);
    const planner = projectTraceStages(state)[0].executorRuns[0];
    expect(planner.memoryContext?.context).toHaveLength(3);
    expect(planner.memoryContext?.owner).toEqual({
      kind: 'planner',
      id: 'plan',
    });
    expect(planner.memoryContext?.scopeGroups?.map(row => row.scope)).toEqual([
      'company',
      'project',
    ]);
    expect(memoryContextFromTool(planner.calls[0])?.context).toHaveLength(1);
  });

  it('preserves empty and failed scope groups for inspection', () => {
    const memory = memoryContextFromPayload({
      memory_owner: 'task',
      memory_owner_id: 'continued-task',
      memory_context: [
        {
          type: 'document_memory',
          groups: [
            group('company', 'Remembered condition'),
            {
              scope_slug: 'empty',
              status: 'completed',
              success: true,
              count: 0,
              items: [],
            },
            {
              scope_slug: 'failed',
              status: 'failed',
              success: false,
              count: 0,
              items: [],
              error: 'Index unavailable',
            },
          ],
        },
      ],
    });
    expect(memory.owner).toEqual({ kind: 'task', id: 'continued-task' });
    expect(memory.scopeGroups).toHaveLength(3);
    expect(memory.scopeGroups?.[2]).toMatchObject({
      scope: 'failed',
      status: 'failed',
      error: 'Index unavailable',
    });
    expect(memory.context).toHaveLength(1);
  });
});
