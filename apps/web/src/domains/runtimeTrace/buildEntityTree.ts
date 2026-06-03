/**
 * Hierarchy Builder: flat SemanticEvent[] → hierarchical TraceEntity tree
 *
 * 3-pass implementation:
 *   Pass 1 — lifecycle events (run_start, orchestrator_start/end, planner_iteration_start/end,
 *             agent_start/end, synthesis_start/end) build a deterministic entity skeleton.
 *   Pass 2 — content events (planner_decision, llm_*, operation_*, error, final_response)
 *             attach to parents via parent_entity_id from event.refs.
 *   Pass 3 — heuristic fallback for events without parent_entity_id (legacy / pre-Stage-1 data).
 */

import type {
  BudgetDelta,
  BudgetSnapshot,
  BuildEntityTreeOptions,
  ContainerDebugRecord,
  EntityData,
  EntityKind,
  PlannerData,
  RunData,
  SubAgentRun,
  TraceEntity,
  AgentData,
  OrchestratorData,
  PhaseData,
  TraceContextSnapshot,
  UnknownData,
} from './entityTypes';
import type { SemanticEvent } from './types';
import { hashEntityIds as hashIds } from './traceIds';
import {
  buildAgentData,
  buildErrorData,
  buildInteractionData,
  buildLLMData,
  buildPlannerData,
  buildRunData,
  buildToolData,
  buildUnknownData,
  enrichPlannerIterationFromStepData,
} from './entityDataBuilders';
import {
  applyBudgetSnapshots,
  aggregateBudgetsBottomUp,
  extractBudgetDelta,
  extractBudgetSnapshot,
  mergeBudgetSnapshots,
  sumBudgetDeltas,
} from './treeBudget';
import { createLegacyContainerAssembler } from './containerAssembler';
import {
  isPhaseRoutedEvent,
  isRuntimeNoiseStep,
  plannerStepToAgentWindowStatus,
  shouldCloseAgentWindowForPlannerStep,
} from './containerRules';
import type { EntityBudget, EntityUsed } from './entityTypes';

function llmBudgetFromEvents(events: SemanticEvent[]): EntityBudget | undefined {
  const used: EntityUsed = {};
  for (const event of events) {
    if (event.raw_type !== 'llm_call' && event.raw_type !== 'llm_turn') continue;
    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const toNum = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
    const inTokens = toNum(raw.tokens_in);
    const outTokens = toNum(raw.tokens_out);
    const totalTokens = toNum(raw.tokens_total);
    if (inTokens !== undefined) used.tokens_in = inTokens;
    if (outTokens !== undefined) used.tokens_out = outTokens;
    if (totalTokens !== undefined) used.tokens_total = totalTokens;
  }
  if (Object.keys(used).length === 0) return undefined;
  return {
    own: used,
    aggregated: { ...used },
    limits: null,
  };
}

function indexEntitiesById(root: TraceEntity): Map<string, TraceEntity> {
  const map = new Map<string, TraceEntity>();
  const visit = (node: TraceEntity): void => {
    map.set(node.id, node);
    for (const child of node.children) visit(child);
  };
  visit(root);
  return map;
}

// ------------------------------------------------------------------
// Pass 1 helpers: lifecycle entity skeleton builder
// ------------------------------------------------------------------

const LIFECYCLE_START_TYPES = new Set([
  'run_start', 'orchestrator_start', 'planner_iteration_start', 'agent_start', 'synthesis_start',
]);
const LIFECYCLE_END_TYPES = new Set([
  'run_end', 'orchestrator_end', 'planner_iteration_end', 'agent_end', 'synthesis_end',
]);

function lifecycleEntityKind(rawType: string): EntityKind {
  if (rawType === 'run_start' || rawType === 'run_end') return 'run';
  if (rawType === 'orchestrator_start' || rawType === 'orchestrator_end') return 'orchestrator';
  if (rawType === 'planner_iteration_start' || rawType === 'planner_iteration_end') return 'planner';
  if (rawType === 'agent_start' || rawType === 'agent_end') return 'agent';
  if (rawType === 'synthesis_start' || rawType === 'synthesis_end') return 'orchestrator';
  return 'unknown';
}

function memoryComponentTitle(slug: string): string {
  if (slug === 'facts' || slug === 'fact_extractor') return 'Fact Extractor';
  if (slug === 'conversation' || slug === 'summary_compactor') return 'Summary Compactor';
  return slug || 'agent';
}

function extractContextSnapshot(raw: Record<string, unknown>): TraceContextSnapshot | undefined {
  const snapshot = raw.context_snapshot;
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return undefined;
  return snapshot as TraceContextSnapshot;
}

function setEntityDepthRecursive(entity: TraceEntity, depth: number): void {
  entity.depth = depth;
  for (const child of entity.children) {
    setEntityDepthRecursive(child, depth + 1);
  }
}

function normalizeRunPhaseLayout(runRoot: TraceEntity): void {
  if (runRoot.kind !== 'run') return;
  const getRole = (node: TraceEntity): string => (
    node.kind === 'orchestrator' && node.data.kind === 'orchestrator'
      ? String(node.data.role ?? '').toLowerCase()
      : ''
  );

  const runChildren = [...runRoot.children];
  let activePhase = runChildren.find((c) => c.kind === 'phase' && c.data.kind === 'phase' && c.data.phaseRole === 'active');
  const moveToActive = runChildren.filter((child) => {
    if (child.kind === 'phase') return false;
    const role = getRole(child);
    if (role === 'memory') return false;
    if (role === 'planner') return true;
    if (role === 'synthesizer') return true;
    return child.kind === 'planner';
  });

  if (!activePhase && moveToActive.length > 0) {
    activePhase = {
      id: hashIds([runRoot.id, 'active-phase']),
      kind: 'phase',
      parentId: runRoot.id,
      depth: runRoot.depth + 1,
      children: [],
      title: 'Подготовка ответа',
      status: 'info',
      sourceEventIds: [],
      data: {
        kind: 'phase',
        phaseRole: 'active',
      } as PhaseData,
    };
    runRoot.children.unshift(activePhase);
  }

  if (activePhase && activePhase.kind === 'phase' && activePhase.data.kind === 'phase') {
    activePhase.title = 'Подготовка ответа';
    for (const child of moveToActive) {
      const idx = runRoot.children.findIndex((c) => c.id === child.id);
      if (idx >= 0) runRoot.children.splice(idx, 1);
      if (!activePhase.children.some((c) => c.id === child.id)) {
        child.parentId = activePhase.id;
        setEntityDepthRecursive(child, activePhase.depth + 1);
        activePhase.children.push(child);
      }
    }

    const synth = [...activePhase.children].reverse().find((c) => getRole(c) === 'synthesizer');
    const plannerFinals = activePhase.children.filter(
      (c) => c.kind === 'planner' && c.data.kind === 'planner' && c.data.stepKind === 'final',
    );
    for (const finalNode of plannerFinals) {
      if (synth && synth.kind === 'orchestrator' && synth.data.kind === 'orchestrator') {
        for (const sid of finalNode.sourceEventIds) {
          if (!synth.sourceEventIds.includes(sid)) synth.sourceEventIds.push(sid);
        }
        if (!synth.data.intent && finalNode.data.kind === 'planner') {
          synth.data.intent = finalNode.data.rationale;
        }
      }
      activePhase.children = activePhase.children.filter((c) => c.id !== finalNode.id);
    }

    let plannerIterationCounter = 1;
    for (const child of activePhase.children) {
      if (getRole(child) === 'synthesizer') {
        child.title = 'Синтезер';
      }
      if (child.kind === 'planner') {
        child.title = `Планер итерация ${plannerIterationCounter}`;
        plannerIterationCounter += 1;
      }
    }
  }

  for (let i = 0; i < runRoot.children.length; i += 1) {
    const child = runRoot.children[i];
    if (child.kind !== 'orchestrator' || child.data.kind !== 'orchestrator') continue;
    if (String(child.data.role ?? '').toLowerCase() !== 'memory') continue;
    const memoryPhase: TraceEntity = {
      ...child,
      kind: 'phase',
      title: 'Мемори',
      data: {
        kind: 'phase',
        phaseRole: 'memory',
      } as PhaseData,
    };
    setEntityDepthRecursive(memoryPhase, runRoot.depth + 1);
    runRoot.children[i] = memoryPhase;
  }

  const deriveStatus = (children: TraceEntity[]): TraceEntity['status'] => {
    if (children.some((c) => c.status === 'error')) return 'error';
    if (children.some((c) => c.status === 'warn')) return 'warn';
    if (children.some((c) => c.status === 'pending')) return 'pending';
    if (children.some((c) => c.status === 'ok')) return 'ok';
    return 'info';
  };
  if (activePhase && activePhase.kind === 'phase') {
    activePhase.sourceEventIds = Array.from(new Set(activePhase.children.flatMap((child) => child.sourceEventIds || [])));
    activePhase.status = deriveStatus(activePhase.children);
  }
  for (const child of runRoot.children) {
    if (child.kind === 'phase') {
      child.sourceEventIds = Array.from(new Set(child.children.flatMap((c) => c.sourceEventIds || [])));
      child.status = deriveStatus(child.children);
    }
  }
}

function buildEntityFromLifecycleStart(event: SemanticEvent): TraceEntity | null {
  const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
  const entityId = (
    typeof raw.entity_id === 'string' ? raw.entity_id :
    typeof raw.slug === 'string' ? raw.slug :
    typeof event.raw?.id === 'string' ? `${event.raw_type}:${event.raw.id}` :
    null
  );
  if (!entityId) return null;

  const kind = lifecycleEntityKind(event.raw_type);
  const rawEntityType = typeof raw.entity_type === 'string' ? raw.entity_type : undefined;
  const derivedRole: string | undefined =
    typeof raw.role === 'string'
      ? raw.role
      : rawEntityType === 'synthesis_run'
        ? 'synthesizer'
        : event.raw_type === 'synthesis_start'
          ? 'synthesizer'
          : event.raw_type === 'orchestrator_start'
            ? 'planner'
            : undefined;
  const agentSlug = typeof raw.agent_slug === 'string' ? raw.agent_slug : undefined;
  const role = derivedRole;
  const slug = agentSlug ?? (typeof raw.slug === 'string' ? raw.slug : entityId);
  const contextSnapshot = extractContextSnapshot(raw);

  let title = slug;
  if (kind === 'planner') {
    const iter = typeof raw.iteration === 'number' ? raw.iteration : 1;
    title = `Step #${iter}`;
  } else if (kind === 'orchestrator') {
    if (role === 'synthesizer') title = 'Synthesis';
    else if (role === 'planner') title = 'Orchestrator';
    else if (role === 'memory') title = 'Memory';
    else title = slug || 'Orchestrator';
  } else if (kind === 'run') {
    title = 'Run';
  } else if (kind === 'agent') {
    title = memoryComponentTitle(agentSlug || 'agent');
  }

  const data: EntityData = (() => {
    if (kind === 'run') {
      return {
        kind: 'run',
        contextSnapshot,
      } as RunData;
    }
    if (kind === 'orchestrator') {
      return {
        kind: 'orchestrator',
        slug: slug,
        role: (role ?? (event.raw_type === 'synthesis_start' ? 'synthesizer' : 'planner')) as OrchestratorData['role'],
        contextSnapshot,
      } as OrchestratorData;
    }
    if (kind === 'planner') {
      const iter = typeof raw.iteration === 'number' ? raw.iteration : 1;
      return {
        kind: 'planner',
        stepKind: 'iteration',
        rationale: `Step iteration ${iter}`,
        contextSnapshot,
      } as PlannerData;
    }
    if (kind === 'agent') {
      return {
        kind: 'agent',
        slug: agentSlug ?? 'unknown',
        prompt: { isBriefMode: false },
        contextSnapshot,
      } as AgentData;
    }
    return { kind: 'unknown', rawType: event.raw_type, raw: raw, hint: '' } as UnknownData;
  })();

  return {
    id: entityId,
    kind,
    parentId: null,
    depth: 0,
    children: [],
    title,
    status: 'info' as const,
    startedAt: event.started_at,
    sourceEventIds: [event.id],
    budgetSnapshot: extractBudgetSnapshot(event),
    data,
  };
}

// ------------------------------------------------------------------
// Stack-based Tree Builder
// ------------------------------------------------------------------

interface StackItem {
  entity: TraceEntity;
  startIndex: number;
}

interface PendingPair {
  type: 'llm' | 'tool';
  startEvent: SemanticEvent;
  events: SemanticEvent[];
}

// ------------------------------------------------------------------
// 3-Pass tree builder (Stage 1 backend: lifecycle events present)
// ------------------------------------------------------------------

function _buildEntityTree3Pass(
  events: SemanticEvent[],
  _options: BuildEntityTreeOptions,
): TraceEntity {
  // ------- Pass 1: build entity skeleton from lifecycle events -------

  // entityById: entity_id → TraceEntity (for all lifecycle-created entities)
  const entityById = new Map<string, TraceEntity>();

  // Root fallback (used only if run_start is missing)
  const root: TraceEntity = {
    id: 'root',
    kind: 'run',
    parentId: null,
    depth: 0,
    children: [],
    title: 'Run',
    status: 'info',
    sourceEventIds: [],
    data: buildRunData(events),
  };
  entityById.set('root', root);

  let runEntity: TraceEntity = root;

  for (const event of events) {
    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;

    // --- handle lifecycle START ---
    if (LIFECYCLE_START_TYPES.has(event.raw_type)) {
      const entity = buildEntityFromLifecycleStart(event);
      if (!entity) continue;

      const parentEntityId = typeof raw.parent_entity_id === 'string' ? raw.parent_entity_id : null;
      const parentEntity = parentEntityId ? (entityById.get(parentEntityId) ?? root) : root;

      if (entity.kind === 'run') {
        // run_start is the true root — don't nest under synthetic root
        entity.parentId = null;
        entity.depth = 0;
        runEntity = entity;
        entityById.set(entity.id, entity);
        continue;
      }
      entity.parentId = parentEntity.id;
      entity.depth = parentEntity.depth + 1;
      parentEntity.children.push(entity);
      entityById.set(entity.id, entity);
      continue;
    }

    // --- handle lifecycle END ---
    if (LIFECYCLE_END_TYPES.has(event.raw_type)) {
      const entityId = (
        typeof raw.entity_id === 'string' ? raw.entity_id :
        typeof raw.slug === 'string' ? raw.slug :
        typeof event.raw?.id === 'string' ? `${event.raw_type.replace('_end', '_start')}:${event.raw.id}` :
        null
      );
      if (!entityId) continue;
      const entity = entityById.get(entityId);
      if (!entity) continue;

      // Update status
      const endStatus = typeof raw.status === 'string' ? raw.status : 'completed';
      if (endStatus === 'failed' || endStatus === 'aborted') {
        entity.status = endStatus === 'aborted' ? 'warn' : 'error';
      } else if (endStatus === 'completed') {
        entity.status = 'ok';
      } else if (endStatus === 'paused') {
        entity.status = 'warn';
      }

      // Duration
      if (entity.startedAt && event.started_at) {
        const startMs = new Date(entity.startedAt).getTime();
        const endMs = new Date(event.started_at).getTime();
        entity.durationMs = Math.max(0, endMs - startMs);
      }
      entity.sourceEventIds.push(event.id);
      continue;
    }
  }

  // If run_start was in events, root was replaced. Else use root directly.
  const treeRoot = runEntity;

  // Ensure run data has correct info (populated from all events)
  if (treeRoot.data.kind === 'run') {
    Object.assign(treeRoot.data, buildRunData(events));
  }

  // ------- Pass 2: attach content events via parent_entity_id -------

  const pendingPairs = new Map<string, PendingPair>();
  const llmEntityByCallId = new Map<string, TraceEntity>();
  const llmEventsByCallId = new Map<string, SemanticEvent[]>();

  for (const event of events) {
    // Skip lifecycle events (already handled in Pass 1)
    if (LIFECYCLE_START_TYPES.has(event.raw_type) || LIFECYCLE_END_TYPES.has(event.raw_type)) continue;

    const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const rawType = event.raw_type;

    // Accumulate budget at root
    const eventBudget = extractBudgetSnapshot(event);
    const eventDelta = extractBudgetDelta(event);
    if (eventBudget) {
      treeRoot.budgetSnapshot = treeRoot.budgetSnapshot
        ? mergeBudgetSnapshots(treeRoot.budgetSnapshot, eventBudget)
        : eventBudget;
    }
    if (eventDelta) {
      treeRoot.budgetDelta = treeRoot.budgetDelta
        ? sumBudgetDeltas(treeRoot.budgetDelta, eventDelta)
        : eventDelta;
    }

    // Resolve parent by parent_entity_id (from refs or raw payload)
    const parentEntityId = (
      typeof event.refs?.parent_entity_id === 'string' ? event.refs.parent_entity_id :
      typeof raw.parent_entity_id === 'string' ? raw.parent_entity_id :
      null
    );
    const resolvedParent = parentEntityId ? (entityById.get(parentEntityId) ?? treeRoot) : treeRoot;

    // --- llm_request: start pending pair ---
    if (rawType === 'llm_request') {
      const llmCallId = _getLlmCallId(event);
      pendingPairs.set(llmCallId, { type: 'llm', startEvent: event, events: [event] });
      llmEventsByCallId.set(llmCallId, [event]);
      continue;
    }

    // --- llm_turn: self-contained llm event ---
    if (rawType === 'llm_turn') {
      const llmCallId = _getLlmCallId(event);
      const pairEvents = [event];
      const llmEntity: TraceEntity = {
        id: hashIds([llmCallId, event.id]),
        kind: 'llm',
        parentId: resolvedParent.id,
        depth: resolvedParent.depth + 1,
        children: [],
        title: event.summary ?? 'LLM',
        status: event.status,
        startedAt: event.started_at,
        durationMs: event.duration_ms ?? 0,
        sourceEventIds: [event.id],
        budgetSnapshot: extractBudgetSnapshot(event),
        budget: llmBudgetFromEvents(pairEvents),
        data: buildLLMData(pairEvents),
      };
      resolvedParent.children.push(llmEntity);
      entityById.set(llmEntity.id, llmEntity);
      llmEntityByCallId.set(llmCallId, llmEntity);
      continue;
    }

    // --- llm_response / llm_call: complete llm pair ---
    if (rawType === 'llm_response' || rawType === 'llm_call') {
      const llmCallId = _getLlmCallId(event);
      const pending = pendingPairs.get(llmCallId);
      const knownEvents = llmEventsByCallId.get(llmCallId) ?? pending?.events ?? [];
      const pairEvents = [...knownEvents, event].filter(
        (c, idx, arr) => arr.findIndex(item => item.id === c.id) === idx,
      );
      llmEventsByCallId.set(llmCallId, pairEvents);

      const existing = llmEntityByCallId.get(llmCallId);
      if (existing) {
        for (const pe of pairEvents) {
          if (!existing.sourceEventIds.includes(pe.id)) existing.sourceEventIds.push(pe.id);
        }
        existing.status = event.status;
        existing.data = buildLLMData(pairEvents);
        const llmBudget = llmBudgetFromEvents(pairEvents);
        if (llmBudget) existing.budget = llmBudget;
      } else {
        const llmEntity: TraceEntity = {
          id: hashIds([llmCallId, ...pairEvents.map(e => e.id)]),
          kind: 'llm',
          parentId: resolvedParent.id,
          depth: resolvedParent.depth + 1,
          children: [],
          title: event.summary ?? 'LLM',
          status: event.status,
          startedAt: pairEvents[0]?.started_at ?? event.started_at,
          durationMs: pairEvents.reduce((acc, cur) => acc + (cur.duration_ms ?? 0), 0),
          sourceEventIds: pairEvents.map(e => e.id),
          budgetSnapshot: extractBudgetSnapshot(event),
          budget: llmBudgetFromEvents(pairEvents),
          data: buildLLMData(pairEvents),
        };
        resolvedParent.children.push(llmEntity);
        entityById.set(llmEntity.id, llmEntity);
        llmEntityByCallId.set(llmCallId, llmEntity);
      }
      if (rawType === 'llm_call') pendingPairs.delete(llmCallId);
      continue;
    }

    // --- operation_call: start pending pair ---
    if (rawType === 'operation_call' || rawType === 'tool_call') {
      const callId = String(raw.call_id ?? event.id);
      pendingPairs.set(callId, { type: 'tool', startEvent: event, events: [event] });
      continue;
    }

    // --- operation_result / tool_result: complete tool pair ---
    if (rawType === 'operation_result' || rawType === 'tool_result') {
      const callId = String(raw.call_id ?? '');
      const pending = callId ? pendingPairs.get(callId) : undefined;
      const pairEvents: SemanticEvent[] = pending ? [...pending.events, event] : [event];

      const toolEntity: TraceEntity = {
        id: hashIds(pairEvents.map(e => e.id)),
        kind: 'tool',
        parentId: resolvedParent.id,
        depth: resolvedParent.depth + 1,
        children: [],
        title: event.summary ?? 'Tool',
        status: event.status,
        startedAt: pending?.startEvent.started_at ?? event.started_at,
        durationMs: (pending?.startEvent.duration_ms ?? 0) + (event.duration_ms ?? 0),
        sourceEventIds: pairEvents.map(e => e.id),
        budgetSnapshot: extractBudgetSnapshot(event),
        budgetDelta: pairEvents
          .map(extractBudgetDelta)
          .filter((v): v is BudgetDelta => !!v)
          .reduce((acc, curr) => sumBudgetDeltas(acc, curr), {} as BudgetDelta),
        data: buildToolData(pairEvents),
      };
      resolvedParent.children.push(toolEntity);
      entityById.set(toolEntity.id, toolEntity);
      if (callId) pendingPairs.delete(callId);
      continue;
    }

    // --- protocol_retry: add to pending tool pair ---
    if (rawType === 'protocol_retry') {
      const recentPending = Array.from(pendingPairs.values()).filter(p => p.type === 'tool').pop();
      if (recentPending) recentPending.events.push(event);
      continue;
    }

    // --- planner_decision: enrich parent planner iteration ---
    if (rawType === 'planner_decision') {
      const plannerData = buildPlannerData(event);
      if (resolvedParent.kind === 'planner' && resolvedParent.data.kind === 'planner') {
        enrichPlannerIterationFromStepData(resolvedParent, plannerData);
        if (!resolvedParent.sourceEventIds.includes(event.id)) resolvedParent.sourceEventIds.push(event.id);
      } else {
        const decision: TraceEntity = {
          id: hashIds([event.id]),
          kind: 'planner',
          parentId: resolvedParent.id,
          depth: resolvedParent.depth + 1,
          children: [],
          title: `${plannerData.stepKind}: ${plannerData.rationale ?? ''}`.slice(0, 80),
          status: event.status,
          startedAt: event.started_at,
          durationMs: event.duration_ms,
          sourceEventIds: [event.id],
          budgetSnapshot: extractBudgetSnapshot(event),
          data: plannerData,
        };
        resolvedParent.children.push(decision);
        entityById.set(decision.id, decision);
      }
      continue;
    }

    // --- error ---
    if (rawType === 'question_answer') {
      const interactionEntity: TraceEntity = {
        id: String(raw.entity_id ?? hashIds([event.id])),
        kind: 'interaction',
        parentId: resolvedParent.id,
        depth: resolvedParent.depth + 1,
        children: [],
        title: event.summary ?? 'Question answered',
        status: event.status,
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: [event.id],
        data: buildInteractionData(event),
      };
      resolvedParent.children.push(interactionEntity);
      entityById.set(interactionEntity.id, interactionEntity);
      continue;
    }

    // --- error ---
    if (rawType === 'error') {
      const errorEntity: TraceEntity = {
        id: hashIds([event.id]),
        kind: 'error',
        parentId: resolvedParent.id,
        depth: resolvedParent.depth + 1,
        children: [],
        title: event.summary ?? 'Error',
        status: 'error',
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: [event.id],
        data: buildErrorData(event),
      };
      resolvedParent.children.push(errorEntity);
      entityById.set(errorEntity.id, errorEntity);
      // propagate error status up
      let p: TraceEntity | undefined = resolvedParent;
      while (p) {
        if (p.status !== 'error') p.status = 'warn';
        p = p.parentId ? entityById.get(p.parentId) : undefined;
      }
      continue;
    }

    // --- final_response / final ---
    if (rawType === 'final_response' || rawType === 'final') {
      if (resolvedParent.kind === 'orchestrator' && resolvedParent.data.kind === 'orchestrator') {
        resolvedParent.status = event.status;
        if (!resolvedParent.sourceEventIds.includes(event.id)) resolvedParent.sourceEventIds.push(event.id);
        if (resolvedParent.data.role === 'synthesizer') {
          resolvedParent.data.intent = String(event.outputs?.content ?? '');
        }
      } else {
        const finalEntity: TraceEntity = {
          id: hashIds([event.id]),
          kind: 'planner',
          parentId: resolvedParent.id,
          depth: resolvedParent.depth + 1,
          children: [],
          title: 'Final response',
          status: event.status,
          startedAt: event.started_at,
          durationMs: event.duration_ms,
          sourceEventIds: [event.id],
          data: {
            kind: 'planner',
            stepKind: 'final',
            rationale: String(event.outputs?.content ?? ''),
          },
        };
        resolvedParent.children.push(finalEntity);
        entityById.set(finalEntity.id, finalEntity);
      }
      // Update run data
      if (treeRoot.data.kind === 'run') {
        treeRoot.data.finalContent = event.outputs?.content as string | undefined ?? treeRoot.data.finalContent;
      }
      continue;
    }

    // --- all other events: attach to parent as sourceEventIds metadata ---
    if (!resolvedParent.sourceEventIds.includes(event.id)) {
      resolvedParent.sourceEventIds.push(event.id);
    }
    const budget = extractBudgetSnapshot(event);
    if (budget) {
      resolvedParent.budgetSnapshot = resolvedParent.budgetSnapshot
        ? mergeBudgetSnapshots(resolvedParent.budgetSnapshot, budget)
        : budget;
    }
  }

  // ------- Pass 3: aggregate budgets bottom-up -------
  applyBudgetSnapshots(indexEntitiesById(treeRoot), events);
  aggregateBudgetsBottomUp(treeRoot);
  sortTreeChronologically(treeRoot, buildEventOrderIndex(events));
  normalizeRunPhaseLayout(treeRoot);

  return treeRoot;
}

function _getLlmCallId(event: SemanticEvent): string {
  const raw = (event.raw?.raw ?? {}) as Record<string, unknown>;
  const explicit = raw.llm_call_id ?? event.refs?.llm_call_id;
  if (typeof explicit === 'string' && explicit.trim()) return explicit.trim();
  return `fallback:${event.iteration}:${event.id}`;
}

function buildEventOrderIndex(events: SemanticEvent[]): Map<string, number> {
  const index = new Map<string, number>();
  events.forEach((event, i) => index.set(event.id, i));
  return index;
}

function minEntityEventOrder(entity: TraceEntity, eventOrder: Map<string, number>): number {
  let min = Number.POSITIVE_INFINITY;
  for (const eventId of entity.sourceEventIds) {
    const order = eventOrder.get(eventId);
    if (order !== undefined && order < min) min = order;
  }
  return min;
}

function sortTreeChronologically(entity: TraceEntity, eventOrder: Map<string, number>): void {
  entity.children.sort((a, b) => {
    const aOrder = minEntityEventOrder(a, eventOrder);
    const bOrder = minEntityEventOrder(b, eventOrder);
    if (aOrder !== bOrder) return aOrder - bOrder;
    const aStart = a.startedAt ? new Date(a.startedAt).getTime() : Number.MAX_SAFE_INTEGER;
    const bStart = b.startedAt ? new Date(b.startedAt).getTime() : Number.MAX_SAFE_INTEGER;
    return aStart - bStart;
  });
  for (const child of entity.children) {
    sortTreeChronologically(child, eventOrder);
  }
}

// ------------------------------------------------------------------
export function buildEntityTree(
  events: SemanticEvent[],
  options: BuildEntityTreeOptions = {},
): TraceEntity {
  const { linkSubAgents = false, subAgentRuns = [] } = options;

  // Detect whether stream contains lifecycle events (Stage 1 backend)
  const hasLifecycleEvents = events.some(e => LIFECYCLE_START_TYPES.has(e.raw_type));

  if (hasLifecycleEvents) {
    return _buildEntityTree3Pass(events, options);
  }

  // -----------------------------------------------------------------
  // Legacy heuristic path (no lifecycle events from backend)
  // -----------------------------------------------------------------

  // Create root run entity
  const root: TraceEntity = {
    id: 'root',
    kind: 'run',
    parentId: null,
    depth: 0,
    children: [],
    title: 'Run',
    status: 'info',
    sourceEventIds: events.map(e => e.id),
    data: buildRunData(events),
  };

  const assembler = createLegacyContainerAssembler(root, options);
  const stack = assembler.stack;
  const debugRecords = options.debugRecords;
  const emitDebug = (event: SemanticEvent, action: string, entity?: TraceEntity, note?: string): void => {
    if (!debugRecords) return;
    const record: ContainerDebugRecord = {
      eventId: event.id,
      rawType: event.raw_type,
      phase: event.phase,
      action,
      entityId: entity?.id,
      entityKind: entity?.kind,
      note,
    };
    debugRecords.push(record);
  };

  // Track pending pairs (llm_request waiting for llm_response, etc.)
  const pendingPairs: Map<string, PendingPair> = new Map();
  const llmEntityByCallId: Map<string, TraceEntity> = new Map();
  const llmEventsByCallId: Map<string, SemanticEvent[]> = new Map();
  function pushEntity(entity: TraceEntity): void { assembler.pushEntity(entity, events); }
  function popToDepth(targetDepth: number): void { assembler.popToDepth(targetDepth, events); }
  function ensurePlannerIterationEntity(event: SemanticEvent, includeEventInContainer = true): TraceEntity {
    return assembler.ensurePlannerIterationEntity(event, includeEventInContainer);
  }
  function ensureSynthesisEntity(event: SemanticEvent): TraceEntity { return assembler.ensureSynthesisEntity(event); }
  function enrichPlannerIterationFromStep(container: TraceEntity, plannerData: PlannerData): void {
    enrichPlannerIterationFromStepData(container, plannerData);
  }
  function queuePendingAgent(slug: string, entity: TraceEntity): void { assembler.queuePendingAgent(slug, entity); }
  function resolveAgentForEvent(event: SemanticEvent): TraceEntity | undefined { return assembler.resolveAgentForEvent(event); }
  function resolveParentForEvent(event: SemanticEvent): TraceEntity { return assembler.resolveParentForEvent(event); }
  function getLlmCallId(event: SemanticEvent): string { return assembler.getLlmCallId(event); }
  function closeCurrentAgentWindow(endEvent: SemanticEvent, status: TraceEntity['status'] = 'ok'): void {
    assembler.closeCurrentAgentWindow(endEvent, status);
  }

  // Agent-runs page often has no lifecycle events; synthesize agent container by agent_run_id.
  const firstAgentEvent = events.find((e) => {
    const raw = (e.raw?.raw ?? {}) as Record<string, unknown>;
    return typeof raw.agent_run_id === 'string' && raw.agent_run_id.length > 0;
  });
  if (firstAgentEvent) {
    const raw = (firstAgentEvent.raw?.raw ?? {}) as Record<string, unknown>;
    const syntheticRunId = typeof raw.agent_run_id === 'string' && raw.agent_run_id
      ? raw.agent_run_id
      : undefined;
    const syntheticSlug = typeof raw.agent_slug === 'string' && raw.agent_slug
      ? raw.agent_slug
      : 'agent';
    if (syntheticRunId) {
      const syntheticAgent: TraceEntity = {
        id: hashIds([syntheticRunId, 'synthetic-agent']),
        kind: 'agent',
        parentId: root.id,
        depth: 1,
        children: [],
        title: syntheticSlug,
        status: 'info',
        startedAt: firstAgentEvent.started_at,
        sourceEventIds: [],
        data: {
          kind: 'agent',
          slug: syntheticSlug,
          prompt: { isBriefMode: false },
        } as AgentData,
      };
      root.children.push(syntheticAgent);
      assembler.linkAgentRunId(syntheticRunId, syntheticAgent);
      queuePendingAgent(syntheticSlug, syntheticAgent);
    }
  }

  // Process each event
  for (let i = 0; i < events.length; i++) {
    const event = events[i];
    const category = event.category;
    const rawType = event.raw_type;
    const rawPayload = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const stage = String(rawPayload.stage ?? '').toLowerCase();
    const eventAgentRunId = typeof rawPayload.agent_run_id === 'string' ? rawPayload.agent_run_id : undefined;

    const currentAgentWindow = assembler.getCurrentAgentWindow();
    if (event.phase === 'agent' && eventAgentRunId && currentAgentWindow && stack[stack.length - 1].entity.kind === 'agent') {
      assembler.linkAgentRunId(eventAgentRunId, stack[stack.length - 1].entity);
    }
    if (event.phase === 'agent') {
      resolveAgentForEvent(event);
    }

    if ((event.phase === 'planner' || event.phase === 'synthesis') && assembler.getCurrentAgentWindow()) {
      closeCurrentAgentWindow(event, 'ok');
      emitDebug(event, 'close_agent_window', undefined, 'phase_switch');
    }

    // Global budget accumulation at run level for a consistent budget tab
    const eventBudget = extractBudgetSnapshot(event);
    const eventDelta = extractBudgetDelta(event);
    if (eventBudget) {
      root.budgetSnapshot = root.budgetSnapshot
        ? mergeBudgetSnapshots(root.budgetSnapshot, eventBudget)
        : eventBudget;
    }
    if (eventDelta) {
      root.budgetDelta = root.budgetDelta
        ? sumBudgetDeltas(root.budgetDelta, eventDelta)
        : eventDelta;
    }

    // --- Handle orchestrator_start (backend Stage 1) ---
    if (rawType === 'orchestrator_start') {
      const rawEvent = (event.raw?.raw ?? {}) as Record<string, unknown>;
      const slug = String(rawEvent.slug ?? rawEvent.role ?? 'orchestrator');
      const orchestrator: TraceEntity = {
        id: hashIds([event.id]),
        kind: 'orchestrator',
        parentId: null, // set by pushEntity
        depth: 0,
        children: [],
        title: slug,
        status: event.status === 'error' ? 'error' : 'info',
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: [event.id],
        budgetSnapshot: extractBudgetSnapshot(event),
        data: {
          kind: 'orchestrator',
          slug,
          role: rawEvent.role as OrchestratorData['role'] ?? undefined,
          intent: typeof rawEvent.intent === 'string' ? rawEvent.intent : undefined,
          contextSnapshot: extractContextSnapshot(rawEvent),
        },
      };
      pushEntity(orchestrator);
      emitDebug(event, 'open_orchestrator', orchestrator);
      continue;
    }

    // --- Handle orchestrator_end (backend Stage 1) ---
    if (rawType === 'orchestrator_end') {
      popToDepth(1); // Pop to root level
      emitDebug(event, 'close_orchestrator');
      continue;
    }

    // --- Handle agent_start (backend Stage 1) ---
    if (rawType === 'agent_start') {
      const rawEvent = (event.raw?.raw ?? {}) as Record<string, unknown>;
      const slug = String(rawEvent.agent_slug ?? rawEvent.slug ?? 'agent');
      const agent: TraceEntity = {
        id: hashIds([event.id]),
        kind: 'agent',
        parentId: null,
        depth: 0,
        children: [],
        title: slug,
        status: 'pending',
        startedAt: event.started_at,
        sourceEventIds: [event.id],
        data: {
          kind: 'agent',
          slug,
          prompt: { isBriefMode: false },
          contextSnapshot: extractContextSnapshot(rawEvent),
        } as AgentData,
      };
      pushEntity(agent);
      emitDebug(event, 'open_agent', agent);
      continue;
    }

    // --- Handle agent_end (backend Stage 1) ---
    if (rawType === 'agent_end') {
      // Update agent status from the event before popping
      const endStatus = typeof rawPayload.status === 'string' ? rawPayload.status : 'completed';
      const agentStatus: TraceEntity['status'] =
        endStatus === 'failed' ? 'error' :
        endStatus === 'aborted' ? 'warn' :
        endStatus === 'paused' ? 'warn' :
        endStatus === 'completed' ? 'ok' : 'info';
      // Find and update the most recent agent entity in the stack
      for (let sIdx = stack.length - 1; sIdx >= 0; sIdx--) {
        if (stack[sIdx].entity.kind === 'agent') {
          stack[sIdx].entity.status = agentStatus;
          if (!stack[sIdx].entity.sourceEventIds.includes(event.id)) {
            stack[sIdx].entity.sourceEventIds.push(event.id);
          }
          break;
        }
      }
      // Pop until we exit agent level
      while (stack.length > 2 && stack[stack.length - 1].entity.kind === 'agent') {
        stack.pop();
      }
      emitDebug(event, 'close_agent');
      continue;
    }

    // --- Handle planner_iteration_end (backend Stage 1) ---
    if (rawType === 'planner_iteration_end') {
      const endStatus = typeof rawPayload.status === 'string' ? rawPayload.status : 'completed';
      const plannerStatus: TraceEntity['status'] =
        endStatus === 'failed' ? 'error' :
        endStatus === 'aborted' ? 'warn' :
        endStatus === 'paused' ? 'warn' :
        endStatus === 'completed' ? 'ok' : 'info';
      // Find and update the most recent planner entity in the stack
      for (let sIdx = stack.length - 1; sIdx >= 0; sIdx--) {
        if (stack[sIdx].entity.kind === 'planner') {
          stack[sIdx].entity.status = plannerStatus;
          if (!stack[sIdx].entity.sourceEventIds.includes(event.id)) {
            stack[sIdx].entity.sourceEventIds.push(event.id);
          }
          break;
        }
      }
      emitDebug(event, 'close_planner_iteration');
      continue;
    }

    if (event.phase === 'planner' && rawType === 'status' && stage.includes('planner')) {
      const plannerEntity = ensurePlannerIterationEntity(event);
      emitDebug(event, 'route_planner_status', plannerEntity, stage);
      continue;
    }

    // --- Handle planner_decision ---
    if (rawType === 'planner_decision') {
      const plannerData = buildPlannerData(event);
      const plannerContainer = event.phase === 'planner' ? ensurePlannerIterationEntity(event, false) : null;

      if (plannerContainer) {
        // Planner iteration is the business-step container; planner_decision is a raw step inside it.
        if (!plannerContainer.sourceEventIds.includes(event.id)) plannerContainer.sourceEventIds.push(event.id);
        const budget = extractBudgetSnapshot(event);
        if (budget) {
          plannerContainer.budgetSnapshot = plannerContainer.budgetSnapshot
            ? mergeBudgetSnapshots(plannerContainer.budgetSnapshot, budget)
            : budget;
        }
        enrichPlannerIterationFromStep(plannerContainer, plannerData);
        emitDebug(event, 'planner_decision_to_container', plannerContainer, plannerData.stepKind);
      } else {
        const decision: TraceEntity = {
          id: hashIds([event.id]),
          kind: 'planner',
          parentId: null,
          depth: 0,
          children: [],
          title: `${plannerData.stepKind}: ${plannerData.rationale ?? ''}`.slice(0, 80),
          status: event.status,
          startedAt: event.started_at,
          durationMs: event.duration_ms,
          sourceEventIds: [event.id],
          budgetSnapshot: extractBudgetSnapshot(event),
          data: plannerData,
        };
        const parent = stack[stack.length - 1];
        decision.parentId = parent.entity.id;
        decision.depth = parent.entity.depth + 1;
        parent.entity.children.push(decision);
        emitDebug(event, 'planner_decision_entity', decision, plannerData.stepKind);
      }

      // --- Heuristic: call_agent starts agent window ---
      if (plannerData.stepKind === 'call_agent' && !assembler.getCurrentAgentWindow()) {
        // Close any previous agent
        while (stack.length > 2 && stack[stack.length - 1].entity.kind === 'agent') {
          stack.pop();
        }

        // Find matching sub-agent run if linking enabled
        const agentSlug = plannerData.decision?.chosenAgentSlug ?? '';
        const matchingSubAgent = linkSubAgents
          ? subAgentRuns.find(r => r.agentSlug === agentSlug && r.parentRunId === 'root' /* matched via heuristic */)
          : undefined;

        // Create agent entity
        const agentEntity: TraceEntity = {
          id: hashIds([event.id, 'agent']),
          kind: 'agent',
          parentId: null,
          depth: 0,
          children: [],
          title: agentSlug || 'agent',
          status: 'pending',
          startedAt: event.started_at,
          sourceEventIds: [event.id],
          data: buildAgentData([event], matchingSubAgent),
        };

        if (plannerContainer) {
          agentEntity.parentId = plannerContainer.id;
          agentEntity.depth = plannerContainer.depth + 1;
          plannerContainer.children.push(agentEntity);
          stack.push({ entity: agentEntity, startIndex: i });
        } else {
          pushEntity(agentEntity);
        }
        const plannerRaw = (event.raw?.raw ?? {}) as Record<string, unknown>;
        const plannerAgentRunId = plannerRaw.agent_run_id;
        if (typeof plannerAgentRunId === 'string' && plannerAgentRunId) {
          assembler.linkAgentRunId(plannerAgentRunId, agentEntity);
        } else if (agentSlug) {
          queuePendingAgent(agentSlug, agentEntity);
        }
        assembler.setCurrentAgentWindow({ startIdx: i, events: [event], plannerStep: event });
        emitDebug(event, 'open_agent_window', agentEntity, agentSlug);
      }

      // --- Heuristic: final/abort/ask_user closes agent window ---
      if (shouldCloseAgentWindowForPlannerStep(plannerData.stepKind)) {
        if (assembler.getCurrentAgentWindow()) {
          closeCurrentAgentWindow(event, plannerStepToAgentWindowStatus(plannerData.stepKind));
          emitDebug(event, 'close_agent_window', undefined, plannerData.stepKind);
        }
      }

      continue;
    }

    // --- Handle final_response: close agent window ---
    if (rawType === 'final_response' || rawType === 'final') {
      if (assembler.getCurrentAgentWindow()) closeCurrentAgentWindow(event, event.status === 'error' ? 'error' : 'ok');

      if (event.phase === 'synthesis') {
        const synthesisParent = ensureSynthesisEntity(event);
        if (!synthesisParent.sourceEventIds.includes(event.id)) synthesisParent.sourceEventIds.push(event.id);
        synthesisParent.status = event.status;
        if (synthesisParent.data.kind === 'orchestrator') {
          synthesisParent.data.intent = String(event.outputs?.content ?? '');
        }
        emitDebug(event, 'route_final_to_synthesis', synthesisParent);
      } else if (event.phase === 'agent') {
        const parent = resolveParentForEvent(event);
        const finalEntity: TraceEntity = {
          id: hashIds([event.id]),
          kind: 'planner',
          parentId: parent.id,
          depth: parent.depth + 1,
          children: [],
          title: 'Final response',
          status: event.status,
          startedAt: event.started_at,
          durationMs: event.duration_ms,
          sourceEventIds: [event.id],
          data: {
            kind: 'planner',
            stepKind: 'final',
            rationale: String(event.outputs?.content ?? ''),
          },
        };
        parent.children.push(finalEntity);
        emitDebug(event, 'route_final_to_agent', parent);
      } else {
        const finalEntity: TraceEntity = {
          id: hashIds([event.id]),
          kind: 'planner',
          parentId: root.id,
          depth: 1,
          children: [],
          title: 'Final response',
          status: event.status,
          startedAt: event.started_at,
          durationMs: event.duration_ms,
          sourceEventIds: [event.id],
          data: {
            kind: 'planner',
            stepKind: 'final',
            rationale: String(event.outputs?.content ?? ''),
          },
        };
        root.children.push(finalEntity);
        emitDebug(event, 'create_final_entity', finalEntity);
      }
      continue;
    }

    // --- Handle llm_request (start pending pair) ---
    if (rawType === 'llm_request') {
      const llmCallId = getLlmCallId(event);
      pendingPairs.set(llmCallId, { type: 'llm', startEvent: event, events: [event] });
      llmEventsByCallId.set(llmCallId, [event]);
      emitDebug(event, 'open_llm_pair', undefined, llmCallId);
      continue;
    }

    // --- Handle llm_turn (self-contained) ---
    if (rawType === 'llm_turn') {
      const llmCallId = getLlmCallId(event);
      const pairEvents = [event];
      const llmEntity: TraceEntity = {
        id: hashIds([llmCallId, event.id]),
        kind: 'llm',
        parentId: null,
        depth: 0,
        children: [],
        title: event.summary ?? 'LLM',
        status: event.status,
        startedAt: event.started_at,
        durationMs: event.duration_ms ?? 0,
        sourceEventIds: [event.id],
        budgetSnapshot: extractBudgetSnapshot(event),
        budget: llmBudgetFromEvents(pairEvents),
        data: buildLLMData(pairEvents),
      };

      const parent = resolveParentForEvent(event);
      llmEntity.parentId = parent.id;
      llmEntity.depth = parent.depth + 1;
      parent.children.push(llmEntity);
      llmEntityByCallId.set(llmCallId, llmEntity);
      emitDebug(event, 'create_llm_turn_entity', llmEntity, llmCallId);

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Handle llm_response / llm_call (complete llm pair) ---
    if (rawType === 'llm_response' || rawType === 'llm_call') {
      const llmCallId = getLlmCallId(event);
      const pending = pendingPairs.get(llmCallId);
      const knownEvents = llmEventsByCallId.get(llmCallId) ?? pending?.events ?? [];
      const pairEvents = [...knownEvents, event].filter(
        (candidate, idx, arr) => arr.findIndex(item => item.id === candidate.id) === idx,
      );
      llmEventsByCallId.set(llmCallId, pairEvents);

      const existingEntity = llmEntityByCallId.get(llmCallId);
      if (existingEntity) {
        for (const pe of pairEvents) {
          if (!existingEntity.sourceEventIds.includes(pe.id)) existingEntity.sourceEventIds.push(pe.id);
        }
        existingEntity.status = event.status;
        existingEntity.durationMs = pairEvents.reduce((acc, current) => acc + (current.duration_ms ?? 0), 0);
        existingEntity.data = buildLLMData(pairEvents);
        const llmBudget = llmBudgetFromEvents(pairEvents);
        if (llmBudget) existingEntity.budget = llmBudget;
      } else {
        const llmEntity: TraceEntity = {
          id: hashIds([llmCallId, ...pairEvents.map(e => e.id)]),
          kind: 'llm',
          parentId: null,
          depth: 0,
          children: [],
          title: event.summary ?? 'LLM',
          status: event.status,
          startedAt: pairEvents[0]?.started_at ?? event.started_at,
          durationMs: pairEvents.reduce((acc, current) => acc + (current.duration_ms ?? 0), 0),
          sourceEventIds: pairEvents.map(e => e.id),
          budgetSnapshot: extractBudgetSnapshot(event),
          budget: llmBudgetFromEvents(pairEvents),
          data: buildLLMData(pairEvents),
        };

        const parent = resolveParentForEvent(event);
        llmEntity.parentId = parent.id;
        llmEntity.depth = parent.depth + 1;
        parent.children.push(llmEntity);
        llmEntityByCallId.set(llmCallId, llmEntity);
        emitDebug(event, 'create_llm_entity', llmEntity, llmCallId);
      }

      if (rawType === 'llm_call') pendingPairs.delete(llmCallId);
      if (rawType === 'llm_call') emitDebug(event, 'close_llm_pair', undefined, llmCallId);

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Handle operation_call (start pending tool pair) ---
    if (rawType === 'operation_call' || rawType === 'tool_call') {
      const callId = String(event.raw?.raw?.call_id ?? event.id);
      pendingPairs.set(callId, { type: 'tool', startEvent: event, events: [event] });
      emitDebug(event, 'open_tool_pair', undefined, callId);
      continue;
    }

    // --- Handle operation_result / tool_result (complete tool pair) ---
    if (rawType === 'operation_result' || rawType === 'tool_result') {
      const callId = String(event.raw?.raw?.call_id ?? '');
      const pending = callId ? pendingPairs.get(callId) : undefined;

      const pairEvents: SemanticEvent[] = pending ? [...pending.events, event] : [event];

      const toolEntity: TraceEntity = {
        id: hashIds(pairEvents.map(e => e.id)),
        kind: 'tool',
        parentId: null,
        depth: 0,
        children: [],
        title: event.summary ?? 'Tool',
        status: event.status,
        startedAt: pending?.startEvent.started_at ?? event.started_at,
        durationMs: (pending?.startEvent.duration_ms ?? 0) + (event.duration_ms ?? 0),
        sourceEventIds: pairEvents.map(e => e.id),
        budgetSnapshot: extractBudgetSnapshot(event),
        budgetDelta: pairEvents
          .map(extractBudgetDelta)
          .filter((v): v is BudgetDelta => !!v)
          .reduce((acc, curr) => sumBudgetDeltas(acc, curr), {} as BudgetDelta),
        data: buildToolData(pairEvents),
      };

      // Attach to agent by explicit agent_run_id when available, fallback to current context.
      const toolData = toolEntity.data;
      const explicitAgentRunId = toolData.kind === 'tool' ? toolData.calledByAgentRunId : undefined;
      const explicitAgentSlug = toolData.kind === 'tool' ? toolData.calledByAgentSlug : undefined;
      const explicitAgent = explicitAgentRunId ? assembler.getAgentByRunId(explicitAgentRunId) : undefined;
      if (explicitAgent) {
        toolEntity.parentId = explicitAgent.id;
        toolEntity.depth = explicitAgent.depth + 1;
        explicitAgent.children.push(toolEntity);
        emitDebug(event, 'create_tool_entity', toolEntity, 'explicit_agent');
      } else {
        const parent = resolveParentForEvent(event);
        toolEntity.parentId = parent.id;
        toolEntity.depth = parent.depth + 1;
        parent.children.push(toolEntity);
        emitDebug(event, 'create_tool_entity', toolEntity, 'stack_parent');
        if (parent.kind === 'agent' && explicitAgentRunId) {
          assembler.linkAgentRunId(explicitAgentRunId, parent);
        } else if (parent.kind === 'agent' && explicitAgentSlug) {
          const parentData = parent.data;
          if (parentData.kind === 'agent' && parentData.slug === explicitAgentSlug && explicitAgentRunId) {
            assembler.linkAgentRunId(explicitAgentRunId, parent);
          }
        }
      }

      // Remove from pending
      if (callId) pendingPairs.delete(callId);
      if (callId) emitDebug(event, 'close_tool_pair', undefined, callId);

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Handle protocol_retry (add to pending tool pair) ---
    if (rawType === 'protocol_retry') {
      // Find recent pending tool pair and add retry
      const recentPending = Array.from(pendingPairs.values())
        .filter(p => p.type === 'tool')
        .pop();
      if (recentPending) {
        recentPending.events.push(event);
      }

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Handle error events ---
    if (rawType === 'question_answer') {
      const interactionEntity: TraceEntity = {
        id: String((event.raw?.raw?.entity_id as string | undefined) ?? hashIds([event.id])),
        kind: 'interaction',
        parentId: null,
        depth: 0,
        children: [],
        title: event.summary ?? 'Question answered',
        status: event.status,
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: [event.id],
        data: buildInteractionData(event),
      };

      const parent = resolveParentForEvent(event);
      interactionEntity.parentId = parent.id;
      interactionEntity.depth = parent.depth + 1;
      parent.children.push(interactionEntity);

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Handle error events ---
    if (rawType === 'error') {
      const errorEntity: TraceEntity = {
        id: hashIds([event.id]),
        kind: 'error',
        parentId: null,
        depth: 0,
        children: [],
        title: event.summary ?? 'Error',
        status: 'error',
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: [event.id],
        data: buildErrorData(event),
      };

      const parent = resolveParentForEvent(event);
      errorEntity.parentId = parent.id;
      errorEntity.depth = parent.depth + 1;
      parent.children.push(errorEntity);

      // Propagate error status up the stack
      for (let j = stack.length - 1; j >= 0; j--) {
        const item = stack[j];
        if (item.entity.status !== 'error') {
          item.entity.status = 'warn';
        }
      }

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Handle status/system runtime markers via phase-first routing ---
    if (rawType === 'status') {
      if (isPhaseRoutedEvent(event)) {
        const parent = resolveParentForEvent(event);
        if (!parent.sourceEventIds.includes(event.id)) parent.sourceEventIds.push(event.id);
        const budget = extractBudgetSnapshot(event);
        if (budget) {
          parent.budgetSnapshot = parent.budgetSnapshot
            ? mergeBudgetSnapshots(parent.budgetSnapshot, budget)
            : budget;
        }
        const delta = extractBudgetDelta(event);
        if (delta) {
          parent.budgetDelta = parent.budgetDelta
            ? sumBudgetDeltas(parent.budgetDelta, delta)
            : delta;
        }
        emitDebug(event, 'route_status_to_container', parent, stage || event.phase);
        { const activeWindow = assembler.getCurrentAgentWindow(); if (activeWindow) activeWindow.events.push(event); }
        continue;
      }
    }

    // --- Handle unknown / unclassified ---
    if (category === 'system' || !['input', 'budget', 'llm', 'decision', 'retry', 'operation', 'policy', 'planner', 'final', 'error'].includes(category)) {
      if (isPhaseRoutedEvent(event)) {
        { const activeWindow = assembler.getCurrentAgentWindow(); if (activeWindow) activeWindow.events.push(event); }
        continue;
      }
      // Skip pure status noise, but capture meaningful system events
      if (isRuntimeNoiseStep(rawType)) {
        // Runtime noise — skip as separate entity, but attach metadata if needed
        emitDebug(event, 'skip_runtime_noise');
        continue;
      }

      // Create unknown entity for truly unclassified events
      const unknownEntity: TraceEntity = {
        id: hashIds([event.id]),
        kind: 'unknown',
        parentId: null,
        depth: 0,
        children: [],
        title: event.title ?? `Unknown: ${rawType}`,
        status: 'warn',
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: [event.id],
        data: buildUnknownData(event),
      };

      const parent = stack[stack.length - 1];
      unknownEntity.parentId = parent.entity.id;
      unknownEntity.depth = parent.entity.depth + 1;
      parent.entity.children.push(unknownEntity);

      const activeWindow = assembler.getCurrentAgentWindow();
      if (activeWindow) {
        activeWindow.events.push(event);
      }
      continue;
    }

    // --- Default: budget and other events attach to current context ---
    const activeWindow = assembler.getCurrentAgentWindow();
    if (activeWindow) {
      activeWindow.events.push(event);
    }
  }

  // Clean up: close any remaining open windows
  while (stack.length > 1) {
    const item = stack.pop();
    if (item && item.entity.durationMs === undefined) {
      const lastEvent = events[events.length - 1];
      const firstEvent = events[item.startIndex];
      if (firstEvent?.started_at && lastEvent?.started_at) {
        const startMs = new Date(firstEvent.started_at).getTime();
        const endMs = new Date(lastEvent.started_at).getTime();
        item.entity.durationMs = Math.max(0, endMs - startMs);
      }
    }
  }

  applyBudgetSnapshots(indexEntitiesById(root), events);
  aggregateBudgetsBottomUp(root);
  sortTreeChronologically(root, buildEventOrderIndex(events));

  return root;
}

// ------------------------------------------------------------------
// Export helpers for tests and UI
// ------------------------------------------------------------------

export function flattenEntityTree(root: TraceEntity): TraceEntity[] {
  const result: TraceEntity[] = [root];
  for (const child of root.children) {
    result.push(...flattenEntityTree(child));
  }
  return result;
}

export function findEntityById(root: TraceEntity, id: string): TraceEntity | undefined {
  if (root.id === id) return root;
  for (const child of root.children) {
    const found = findEntityById(child, id);
    if (found) return found;
  }
  return undefined;
}

export function getEntityPath(root: TraceEntity, id: string): TraceEntity[] {
  const target = findEntityById(root, id);
  if (!target) return [];

  const path: TraceEntity[] = [];
  let current: TraceEntity | undefined = target;
  while (current) {
    path.unshift(current);
    if (current.parentId === null) break;
    current = current.parentId === root.id
      ? root
      : findEntityById(root, current.parentId);
  }
  return path;
}
