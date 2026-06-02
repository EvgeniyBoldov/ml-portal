import { describe, expect, it } from 'vitest';
import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { getSnapshotScopedSteps } from './snapshotSelectors';

interface TestStep {
  id: string;
  type: string;
  data: Record<string, unknown>;
  timestamp: number;
}

function makeEntity(overrides: Partial<TraceEntity>): TraceEntity {
  return {
    id: overrides.id ?? 'entity-1',
    kind: overrides.kind ?? 'unknown',
    parentId: overrides.parentId ?? null,
    depth: overrides.depth ?? 0,
    children: overrides.children ?? [],
    title: overrides.title ?? 'Entity',
    status: overrides.status ?? 'info',
    sourceEventIds: overrides.sourceEventIds ?? [],
    data: overrides.data ?? { kind: 'unknown', rawType: 'unknown', raw: {}, hint: '' },
  };
}

function step(id: string, type: string, data: Record<string, unknown>): TestStep {
  return { id, type, data, timestamp: 0 };
}

describe('getSnapshotScopedSteps', () => {
  it('returns all run steps for the run root inspector', () => {
    const entity = makeEntity({
      id: 'run-1',
      kind: 'run',
      data: { kind: 'run', userRequest: 'test' },
    });
    const steps = [
      step('run-start', 'run_start', {}),
      step('planner-step', 'planner_decision', { planner_iteration_id: 'iter-1' }),
      step('run-end', 'run_end', {}),
    ];

    const scoped = getSnapshotScopedSteps(entity, steps);

    expect(scoped.map((item) => item.id)).toEqual(['run-start', 'planner-step', 'run-end']);
  });

  it('keeps agent inspection inside the selected agent window', () => {
    const entity = makeEntity({
      id: 'agent-viewer',
      kind: 'agent',
      sourceEventIds: ['agent-start', 'agent-end'],
      data: { kind: 'agent', slug: 'viewer', prompt: { isBriefMode: false } },
    });
    const steps = [
      step('agent-start', 'agent_start', { agent_slug: 'viewer' }),
      step('viewer-op', 'operation_call', { parent_entity_id: 'agent-viewer', operation_slug: 'viewer.search' }),
      step('viewer-result', 'operation_result', { parent_entity_id: 'agent-viewer', operation_slug: 'viewer.search' }),
      step('agent-end', 'agent_end', { agent_slug: 'viewer' }),
      step('other-start', 'agent_start', { agent_slug: 'other' }),
      step('other-op', 'operation_call', { parent_entity_id: 'agent-other', operation_slug: 'other.search' }),
    ];

    const scoped = getSnapshotScopedSteps(entity, steps);

    expect(scoped.map((item) => item.id)).toEqual(['agent-start', 'viewer-op', 'viewer-result', 'agent-end']);
  });

  it('pulls planner-related snapshots by planner iteration id', () => {
    const entity = makeEntity({
      id: 'planner-1',
      kind: 'planner',
      sourceEventIds: ['planner-start', 'planner-decision', 'planner-end'],
      data: { kind: 'planner', stepKind: 'call_agent' },
    });
    const steps = [
      step('planner-start', 'planner_iteration_start', { planner_iteration_id: 'iter-1', planner_run_id: 'run-1' }),
      step('planner-decision', 'planner_decision', { planner_iteration_id: 'iter-1', planner_run_id: 'run-1' }),
      step('planner-end', 'planner_iteration_end', { planner_iteration_id: 'iter-1', planner_run_id: 'run-1' }),
      step('planner-rbac', 'status', { stage: 'planner_rbac_snapshot', planner_iteration_id: 'iter-1', planner_run_id: 'run-1' }),
      step('other-rbac', 'status', { stage: 'planner_rbac_snapshot', planner_iteration_id: 'iter-2', planner_run_id: 'run-2' }),
    ];

    const scoped = getSnapshotScopedSteps(entity, steps);

    expect(scoped.map((item) => item.id)).toContain('planner-rbac');
    expect(scoped.map((item) => item.id)).not.toContain('other-rbac');
  });

  it('includes descendant entity steps for synthetic phase inspectors', () => {
    const entity = makeEntity({
      id: 'phase-memory',
      kind: 'phase',
      data: { kind: 'phase', phaseRole: 'memory' },
      children: [
        makeEntity({
          id: 'memory-facts',
          kind: 'agent',
          sourceEventIds: ['facts-start', 'facts-end'],
          data: { kind: 'agent', slug: 'fact_extractor', prompt: { isBriefMode: false } },
        }),
      ],
    });
    const steps = [
      step('facts-start', 'agent_start', { parent_entity_id: 'phase-memory', agent_slug: 'fact_extractor' }),
      step('facts-llm', 'llm_turn', { parent_entity_id: 'memory-facts' }),
      step('facts-end', 'agent_end', { parent_entity_id: 'phase-memory', agent_slug: 'fact_extractor' }),
      step('other-step', 'llm_turn', { parent_entity_id: 'other-entity' }),
    ];

    const scoped = getSnapshotScopedSteps(entity, steps);

    expect(scoped.map((item) => item.id)).toEqual(['facts-start', 'facts-llm', 'facts-end']);
  });
});
