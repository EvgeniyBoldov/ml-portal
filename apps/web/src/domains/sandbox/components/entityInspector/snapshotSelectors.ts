import type { TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../hooks/useSandboxRun';

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function getStringField(step: RunStep, key: string): string | null {
  const value = toRecord(step.data)[key];
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

function getSourceIndexes(entity: TraceEntity, steps: RunStep[]): number[] {
  const sourceIds = new Set(entity.sourceEventIds ?? []);
  if (sourceIds.size === 0) return [];
  const indexes: number[] = [];
  steps.forEach((step, index) => {
    if (sourceIds.has(step.id)) indexes.push(index);
  });
  return indexes;
}

function collectSubtreeSourceIds(entity: TraceEntity): Set<string> {
  const sourceIds = new Set<string>(entity.sourceEventIds ?? []);
  const stack = [...(entity.children ?? [])];
  while (stack.length > 0) {
    const current = stack.pop()!;
    for (const sourceId of current.sourceEventIds ?? []) sourceIds.add(sourceId);
    if (current.children?.length) stack.push(...current.children);
  }
  return sourceIds;
}

function collectSubtreeEntityIds(entity: TraceEntity): Set<string> {
  const ids = new Set<string>([entity.id]);
  const stack = [...(entity.children ?? [])];
  while (stack.length > 0) {
    const current = stack.pop()!;
    ids.add(current.id);
    if (current.children?.length) stack.push(...current.children);
  }
  return ids;
}

function getPlannerKeys(entity: TraceEntity, steps: RunStep[]): { iterationIds: Set<string>; runIds: Set<string> } {
  const iterationIds = new Set<string>();
  const runIds = new Set<string>();
  const sourceIndexes = getSourceIndexes(entity, steps);
  const sourceWindow = sourceIndexes.length > 0
    ? steps.slice(Math.min(...sourceIndexes), Math.max(...sourceIndexes) + 1)
    : steps;

  sourceWindow.forEach((step) => {
    const iterationId = getStringField(step, 'planner_iteration_id');
    const runId = getStringField(step, 'planner_run_id');
    if (iterationId) iterationIds.add(iterationId);
    if (runId) runIds.add(runId);
  });
  return { iterationIds, runIds };
}

function getAgentKeys(entity: TraceEntity, steps: RunStep[]): { slugs: Set<string>; parentIds: Set<string> } {
  const slugs = new Set<string>();
  const parentIds = new Set<string>([entity.id]);
  if (entity.kind === 'agent' && entity.data.kind === 'agent') {
    const slug = String(entity.data.slug ?? '').trim();
    if (slug) slugs.add(slug);
  }
  steps.forEach((step) => {
    const parentEntityId = getStringField(step, 'parent_entity_id');
    if (parentEntityId === entity.id) parentIds.add(parentEntityId);
    const agentSlug = getStringField(step, 'agent_slug');
    if (agentSlug) slugs.add(agentSlug);
  });
  return { slugs, parentIds };
}

export function getSnapshotScopedSteps(entity: TraceEntity, steps: RunStep[]): RunStep[] {
  if (entity.kind === 'run') return steps;

  const sourceIds = collectSubtreeSourceIds(entity);
  const subtreeEntityIds = collectSubtreeEntityIds(entity);
  const sourceIndexes = getSourceIndexes(entity, steps);
  const plannerKeys = entity.kind === 'planner' ? getPlannerKeys(entity, steps) : null;
  const agentKeys = entity.kind === 'agent' ? getAgentKeys(entity, steps) : null;

  const windowStart = sourceIndexes.length > 0 ? Math.min(...sourceIndexes) : -1;
  const windowEnd = sourceIndexes.length > 0 ? Math.max(...sourceIndexes) : -1;
  const result: RunStep[] = [];
  const seen = new Set<string>();

  const include = (step: RunStep) => {
    if (seen.has(step.id)) return;
    seen.add(step.id);
    result.push(step);
  };

  steps.forEach((step, index) => {
    const record = toRecord(step.data);
    const parentEntityId = typeof record.parent_entity_id === 'string' ? record.parent_entity_id : null;
    const entityId = typeof record.entity_id === 'string' ? record.entity_id : null;
    const plannerIterationId = typeof record.planner_iteration_id === 'string' ? record.planner_iteration_id : null;
    const plannerRunId = typeof record.planner_run_id === 'string' ? record.planner_run_id : null;
    const agentSlug = typeof record.agent_slug === 'string' ? record.agent_slug : null;

    const matchesSource = sourceIds.has(step.id);
    const matchesDirectParent =
      (parentEntityId !== null && subtreeEntityIds.has(parentEntityId)) ||
      (entityId !== null && subtreeEntityIds.has(entityId));
    const matchesWindow = windowStart >= 0 && index >= windowStart && index <= windowEnd;
    const matchesPlanner =
      plannerKeys !== null && (
        (plannerIterationId !== null && plannerKeys.iterationIds.has(plannerIterationId)) ||
        (plannerRunId !== null && plannerKeys.runIds.has(plannerRunId))
      );
    const matchesAgent =
      agentKeys !== null && (
        (parentEntityId !== null && agentKeys.parentIds.has(parentEntityId)) ||
        (agentSlug !== null && agentKeys.slugs.has(agentSlug) && matchesWindow)
      );

    if (matchesSource || matchesDirectParent || matchesWindow || matchesPlanner || matchesAgent) {
      include(step);
    }
  });

  return result;
}
