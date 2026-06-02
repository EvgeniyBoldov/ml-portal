import type { BudgetDelta, BuildEntityTreeOptions, PlannerData, TraceEntity } from './entityTypes';
import type { SemanticEvent } from './types';
import { hashEntityIds } from './traceIds';
import { buildAgentData, enrichPlannerIterationFromStepData } from './entityDataBuilders';
import {
  collectBudgetFromEvents,
  extractBudgetSnapshot,
  mergeBudgetSnapshots,
} from './treeBudget';

interface StackItem {
  entity: TraceEntity;
  startIndex: number;
}

export interface AgentWindow {
  startIdx: number;
  events: SemanticEvent[];
  plannerStep: SemanticEvent;
}

export interface LegacyContainerAssembler {
  stack: StackItem[];
  getCurrentAgentWindow: () => AgentWindow | null;
  pushEntity: (entity: TraceEntity, events: SemanticEvent[]) => void;
  popToDepth: (targetDepth: number, events: SemanticEvent[]) => void;
  ensurePlannerIterationEntity: (event: SemanticEvent, includeEventInContainer?: boolean) => TraceEntity;
  ensureSynthesisEntity: (event: SemanticEvent) => TraceEntity;
  queuePendingAgent: (slug: string, entity: TraceEntity) => void;
  resolveAgentForEvent: (event: SemanticEvent) => TraceEntity | undefined;
  resolveParentForEvent: (event: SemanticEvent) => TraceEntity;
  getLlmCallId: (event: SemanticEvent) => string;
  closeCurrentAgentWindow: (endEvent: SemanticEvent, status?: TraceEntity['status']) => void;
  setCurrentAgentWindow: (window: AgentWindow | null) => void;
  linkAgentRunId: (runId: string, entity: TraceEntity) => void;
  getAgentByRunId: (runId: string) => TraceEntity | undefined;
}

export function createLegacyContainerAssembler(
  root: TraceEntity,
  options: BuildEntityTreeOptions,
): LegacyContainerAssembler {
  const { linkSubAgents = false, subAgentRuns = [] } = options;
  const stack: StackItem[] = [{ entity: root, startIndex: 0 }];
  const plannerByIteration: Map<string, TraceEntity> = new Map();
  const pendingAgentsBySlug: Map<string, TraceEntity[]> = new Map();
  const agentByRunId: Map<string, TraceEntity> = new Map();
  let synthesisEntity: TraceEntity | null = null;
  let currentAgentWindow: AgentWindow | null = null;

  function pushEntity(entity: TraceEntity, events: SemanticEvent[]): void {
    const parent = stack[stack.length - 1];
    entity.parentId = parent.entity.id;
    entity.depth = parent.entity.depth + 1;
    parent.entity.children.push(entity);
    stack.push({ entity, startIndex: events.findIndex(e => e.id === entity.sourceEventIds[0]) });
  }

  function popToDepth(targetDepth: number, events: SemanticEvent[]): void {
    while (stack.length > targetDepth + 1) {
      const item = stack.pop();
      if (!item) continue;
      const endEvent = events[events.length - 1];
      const startEvent = events[item.startIndex];
      if (startEvent?.started_at && endEvent?.started_at) {
        const startMs = new Date(startEvent.started_at).getTime();
        const endMs = new Date(endEvent.started_at).getTime();
        item.entity.durationMs = Math.max(0, endMs - startMs);
      }
    }
  }

  function ensurePlannerIterationEntity(event: SemanticEvent, includeEventInContainer = true): TraceEntity {
    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const plannerIterationId = typeof raw.planner_iteration_id === 'string' && raw.planner_iteration_id
      ? raw.planner_iteration_id
      : null;
    const numericIteration = Math.max(0, Number(event.iteration ?? 0));
    const key = plannerIterationId ?? `iter:${numericIteration}`;
    const existing = plannerByIteration.get(key);
    const budget = extractBudgetSnapshot(event);

    if (existing) {
      if (includeEventInContainer && !existing.sourceEventIds.includes(event.id)) {
        existing.sourceEventIds.push(event.id);
      }
      if (includeEventInContainer && budget) {
        existing.budgetSnapshot = existing.budgetSnapshot
          ? mergeBudgetSnapshots(existing.budgetSnapshot, budget)
          : budget;
      }
      return existing;
    }

    const plannerEntity: TraceEntity = {
      id: hashEntityIds([event.id, `planner-${key}`]),
      kind: 'planner',
      parentId: root.id,
      depth: 1,
      children: [],
      title: `Step #${key || 1}`,
      status: 'info',
      startedAt: event.started_at,
      durationMs: event.duration_ms,
      sourceEventIds: includeEventInContainer ? [event.id] : [],
      budgetSnapshot: budget,
      data: {
        kind: 'planner',
        stepKind: 'iteration',
        rationale: `Step iteration ${numericIteration || 1}`,
      },
    };
    root.children.push(plannerEntity);
    plannerByIteration.set(key, plannerEntity);
    return plannerEntity;
  }

  function ensureSynthesisEntity(event: SemanticEvent): TraceEntity {
    if (synthesisEntity) {
      if (!synthesisEntity.sourceEventIds.includes(event.id)) synthesisEntity.sourceEventIds.push(event.id);
      return synthesisEntity;
    }
    synthesisEntity = {
      id: hashEntityIds([event.id, 'synthesis']),
      kind: 'orchestrator',
      parentId: root.id,
      depth: 1,
      children: [],
      title: 'Synthesis',
      status: 'info',
      startedAt: event.started_at,
      durationMs: event.duration_ms,
      sourceEventIds: [event.id],
      budgetSnapshot: extractBudgetSnapshot(event),
      data: {
        kind: 'orchestrator',
        slug: 'synthesizer',
        role: 'synthesizer',
      },
    };
    root.children.push(synthesisEntity);
    return synthesisEntity;
  }

  function queuePendingAgent(slug: string, entity: TraceEntity): void {
    const key = slug.trim().toLowerCase();
    if (!key) return;
    const list = pendingAgentsBySlug.get(key) ?? [];
    list.push(entity);
    pendingAgentsBySlug.set(key, list);
  }

  function resolveAgentForEvent(event: SemanticEvent): TraceEntity | undefined {
    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const runId = typeof raw.agent_run_id === 'string' ? raw.agent_run_id : undefined;
    const slug = typeof raw.agent_slug === 'string' ? raw.agent_slug : undefined;
    if (runId && agentByRunId.has(runId)) return agentByRunId.get(runId);
    if (runId && slug) {
      const key = slug.trim().toLowerCase();
      const queue = pendingAgentsBySlug.get(key) ?? [];
      const candidate = queue.shift();
      if (queue.length > 0) pendingAgentsBySlug.set(key, queue);
      else pendingAgentsBySlug.delete(key);
      if (candidate) {
        agentByRunId.set(runId, candidate);
        return candidate;
      }
    }
    return undefined;
  }

  function resolveParentForEvent(event: SemanticEvent): TraceEntity {
    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const runId = typeof raw.agent_run_id === 'string' ? raw.agent_run_id : undefined;
    if (runId) {
      const byRun = agentByRunId.get(runId);
      if (byRun) return byRun;
      const byEvent = resolveAgentForEvent(event);
      if (byEvent) return byEvent;
    }
    if (event.phase === 'planner') return ensurePlannerIterationEntity(event);
    if (event.phase === 'synthesis') return ensureSynthesisEntity(event);
    if (event.phase === 'agent') {
      const resolvedAgent = resolveAgentForEvent(event);
      if (resolvedAgent) return resolvedAgent;
    }
    return stack[stack.length - 1].entity;
  }

  function getLlmCallId(event: SemanticEvent): string {
    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const explicit = raw.llm_call_id;
    if (typeof explicit === 'string' && explicit.trim()) return explicit.trim();
    return `fallback:${event.iteration}:${event.id}`;
  }

  function closeCurrentAgentWindow(endEvent: SemanticEvent, status: TraceEntity['status'] = 'ok'): void {
    if (!currentAgentWindow) return;
    while (stack.length > 2 && stack[stack.length - 1].entity.kind === 'agent') {
      const item = stack.pop();
      if (!item) continue;
      const startEvent = currentAgentWindow.events[0];
      if (startEvent.started_at && endEvent.started_at) {
        const startMs = new Date(startEvent.started_at).getTime();
        const endMs = new Date(endEvent.started_at).getTime();
        item.entity.durationMs = Math.max(0, endMs - startMs);
      }
      item.entity.status = status;
      const windowBudget = collectBudgetFromEvents(currentAgentWindow.events);
      if (windowBudget) {
        item.entity.budgetSnapshot = item.entity.budgetSnapshot
          ? mergeBudgetSnapshots(item.entity.budgetSnapshot, windowBudget)
          : windowBudget;
      }
    }
    currentAgentWindow = null;
  }

  function setCurrentAgentWindow(window: AgentWindow | null): void {
    currentAgentWindow = window;
  }

  function linkAgentRunId(runId: string, entity: TraceEntity): void {
    agentByRunId.set(runId, entity);
  }

  return {
    stack,
    getCurrentAgentWindow: () => currentAgentWindow,
    pushEntity,
    popToDepth,
    ensurePlannerIterationEntity,
    ensureSynthesisEntity,
    queuePendingAgent,
    resolveAgentForEvent,
    resolveParentForEvent,
    getLlmCallId,
    closeCurrentAgentWindow,
    setCurrentAgentWindow,
    linkAgentRunId,
    getAgentByRunId: (runId: string) => agentByRunId.get(runId),
  };
}
