/**
 * Hierarchy Builder: flat SemanticEvent[] → hierarchical TraceEntity tree
 *
 * MVP implementation uses heuristics (no backend Stage 1 required).
 * After backend Stage 1, deterministic parent_entity_id will replace heuristics.
 */

import type {
  BudgetDelta,
  BudgetMetric,
  BudgetSnapshot,
  BuildEntityTreeOptions,
  EntityData,
  EntityKind,
  LLMData,
  PlannerData,
  RunData,
  SubAgentRun,
  ToolData,
  TraceEntity,
  AgentData,
  ErrorData,
  OrchestratorData,
  UnknownData,
} from './entityTypes';
import type { SemanticEvent } from './types';

// ------------------------------------------------------------------
// Stable ID generation
// ------------------------------------------------------------------

function hashIds(ids: string[]): string {
  const sorted = [...ids].sort();
  let hash = 0;
  for (let i = 0; i < sorted.length; i++) {
    const str = sorted[i];
    for (let j = 0; j < str.length; j++) {
      const char = str.charCodeAt(j);
      hash = (hash << 5) - hash + char;
      hash = hash & hash; // Convert to 32bit integer
    }
  }
  return `ent_${Math.abs(hash).toString(36)}`;
}

// ------------------------------------------------------------------
// Budget helpers
// ------------------------------------------------------------------

function extractBudgetSnapshot(event: SemanticEvent): BudgetSnapshot | undefined {
  if (!event.budget || typeof event.budget !== 'object') return undefined;
  const b = event.budget as Record<string, unknown>;
  const nestedSnapshot = (typeof b.snapshot === 'object' && b.snapshot)
    ? (b.snapshot as Record<string, unknown>)
    : null;
  const source = nestedSnapshot ?? b;

  const snapshot: BudgetSnapshot = {};

  // Steps / iterations
  if (source.consumed_planner_iterations !== undefined || source.max_planner_iterations !== undefined) {
    snapshot.steps = {
      used: typeof source.consumed_planner_iterations === 'number' ? source.consumed_planner_iterations : 0,
      limit: typeof source.max_planner_iterations === 'number' ? source.max_planner_iterations : undefined,
    };
  }

  // Steps (nested format: steps.{used,limit})
  if (!snapshot.steps && typeof source.steps === 'object' && source.steps) {
    const steps = source.steps as Record<string, unknown>;
    const used = typeof steps.used === 'number' ? steps.used : undefined;
    const limit = typeof steps.limit === 'number' ? steps.limit : undefined;
    if (used !== undefined || limit !== undefined) {
      snapshot.steps = { used: used ?? 0, limit };
    }
  }

  // Tools
  if (source.consumed_tool_calls !== undefined || source.max_tool_calls_total !== undefined) {
    snapshot.tools = {
      used: typeof source.consumed_tool_calls === 'number' ? source.consumed_tool_calls : 0,
      limit: typeof source.max_tool_calls_total === 'number' ? source.max_tool_calls_total : undefined,
    };
  }

  // Tools (nested format: tools.{used,limit})
  if (!snapshot.tools && typeof source.tools === 'object' && source.tools) {
    const tools = source.tools as Record<string, unknown>;
    const used = typeof tools.used === 'number' ? tools.used : undefined;
    const limit = typeof tools.limit === 'number' ? tools.limit : undefined;
    if (used !== undefined || limit !== undefined) {
      snapshot.tools = { used: used ?? 0, limit };
    }
  }

  // Retries (from protocol_retry tracking)
  if (source.retries !== undefined && typeof source.retries !== 'object') {
    snapshot.retries = { used: Number(source.retries), limit: undefined };
  }

  // Retries (nested format: retries.{used,limit})
  if (!snapshot.retries && typeof source.retries === 'object' && source.retries) {
    const retries = source.retries as Record<string, unknown>;
    const used = typeof retries.used === 'number' ? retries.used : undefined;
    const limit = typeof retries.limit === 'number' ? retries.limit : undefined;
    if (used !== undefined || limit !== undefined) {
      snapshot.retries = { used: used ?? 0, limit };
    }
  }

  // Tokens (if available)
  if (source.tokens_in !== undefined || source.tokens_consumed !== undefined) {
    snapshot.tokens = {
      used: Number(source.tokens_consumed ?? source.tokens_in ?? 0),
      limit: typeof source.tokens_limit === 'number' ? source.tokens_limit : undefined,
    };
  }

  // Tokens (nested format: tokens.{used,limit})
  if (!snapshot.tokens && typeof source.tokens === 'object' && source.tokens) {
    const tokens = source.tokens as Record<string, unknown>;
    const used = typeof tokens.used === 'number' ? tokens.used : undefined;
    const limit = typeof tokens.limit === 'number' ? tokens.limit : undefined;
    if (used !== undefined || limit !== undefined) {
      snapshot.tokens = { used: used ?? 0, limit };
    }
  }

  // Wall time
  if (source.remaining_wall_time_ms !== undefined || source.max_wall_time_ms !== undefined) {
    const remaining = typeof source.remaining_wall_time_ms === 'number' ? source.remaining_wall_time_ms : undefined;
    const max = typeof source.max_wall_time_ms === 'number' ? source.max_wall_time_ms : undefined;
    const used = max !== undefined && remaining !== undefined ? Math.max(0, max - remaining) : undefined;
    snapshot.wallTimeMs = {
      used: used ?? 0,
      limit: max,
    };
  }

  // Wall time (nested format: wallTimeMs.{used,limit})
  if (!snapshot.wallTimeMs && typeof source.wall_time_ms === 'object' && source.wall_time_ms) {
    const wallTime = source.wall_time_ms as Record<string, unknown>;
    const used = typeof wallTime.used === 'number' ? wallTime.used : undefined;
    const limit = typeof wallTime.limit === 'number' ? wallTime.limit : undefined;
    if (used !== undefined || limit !== undefined) {
      snapshot.wallTimeMs = { used: used ?? 0, limit };
    }
  }

  if (!snapshot.wallTimeMs && typeof source.wallTimeMs === 'object' && source.wallTimeMs) {
    const wallTime = source.wallTimeMs as Record<string, unknown>;
    const used = typeof wallTime.used === 'number' ? wallTime.used : undefined;
    const limit = typeof wallTime.limit === 'number' ? wallTime.limit : undefined;
    if (used !== undefined || limit !== undefined) {
      snapshot.wallTimeMs = { used: used ?? 0, limit };
    }
  }

  return Object.keys(snapshot).length > 0 ? snapshot : undefined;
}

function extractBudgetDelta(event: SemanticEvent): BudgetDelta | undefined {
  if (!event.budget || typeof event.budget !== 'object') return undefined;
  const b = event.budget as Record<string, unknown>;
  if (!b.delta || typeof b.delta !== 'object') return undefined;
  const d = b.delta as Record<string, unknown>;
  const delta: BudgetDelta = {};

  const addScalar = (key: keyof BudgetDelta, value: unknown) => {
    if (typeof value !== 'number' || value <= 0) return;
    delta[key] = { used: value };
  };

  addScalar('steps', d.steps);
  addScalar('tools', d.tools);
  addScalar('retries', d.retries);
  addScalar('tokens', d.tokens);
  addScalar('wallTimeMs', d.wall_time_ms ?? d.wallTimeMs);

  return Object.keys(delta).length > 0 ? delta : undefined;
}

function mergeBudgetSnapshots(a: BudgetSnapshot, b: BudgetSnapshot): BudgetSnapshot {
  const mergeMetric = (m1?: BudgetMetric, m2?: BudgetMetric): BudgetMetric | undefined => {
    if (!m1 && !m2) return undefined;
    return {
      used: Math.max(m1?.used ?? 0, m2?.used ?? 0),
      limit: m2?.limit ?? m1?.limit,
    };
  };

  return {
    steps: mergeMetric(a.steps, b.steps),
    tools: mergeMetric(a.tools, b.tools),
    retries: mergeMetric(a.retries, b.retries),
    tokens: mergeMetric(a.tokens, b.tokens),
    wallTimeMs: mergeMetric(a.wallTimeMs, b.wallTimeMs),
  };
}

function sumBudgetDeltas(a: BudgetDelta, b: BudgetDelta): BudgetDelta {
  const sumMetric = (m1?: BudgetMetric, m2?: BudgetMetric): BudgetMetric | undefined => {
    if (!m1 && !m2) return undefined;
    return { used: (m1?.used ?? 0) + (m2?.used ?? 0), limit: m2?.limit ?? m1?.limit };
  };
  return {
    steps: sumMetric(a.steps, b.steps),
    tools: sumMetric(a.tools, b.tools),
    retries: sumMetric(a.retries, b.retries),
    tokens: sumMetric(a.tokens, b.tokens),
    wallTimeMs: sumMetric(a.wallTimeMs, b.wallTimeMs),
  };
}

function collectBudgetFromEvents(events: SemanticEvent[]): BudgetSnapshot | undefined {
  let acc: BudgetSnapshot = {};
  for (const event of events) {
    const snap = extractBudgetSnapshot(event);
    if (snap) {
      acc = mergeBudgetSnapshots(acc, snap);
    }
  }
  return Object.keys(acc).length > 0 ? acc : undefined;
}

// ------------------------------------------------------------------
// Entity Data Builders (per kind)
// ------------------------------------------------------------------

function buildLLMData(events: SemanticEvent[]): LLMData {
  const request = events.find(e => e.raw_type === 'llm_request' || e.raw_type === 'llm_call');
  const response = events.find(e => e.raw_type === 'llm_response');

  // Try multiple sources for request data
  const reqRaw = request?.raw?.raw ?? {};
  const reqInputs = request?.inputs ?? {};
  const respRaw = response?.raw?.raw ?? {};
  const respOutputs = response?.outputs ?? {};
  const toString = (value: unknown): string | undefined => (typeof value === 'string' ? value : undefined);
  const toNumber = (value: unknown): number | undefined => (typeof value === 'number' ? value : undefined);
  const toRecordArray = (value: unknown): Array<Record<string, unknown>> | undefined => (
    Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null) : undefined
  );
  const llmCallId = (reqRaw.llm_call_id ?? respRaw.llm_call_id) as string | undefined;
  const parentEntityType = (reqRaw.parent_entity_type ?? respRaw.parent_entity_type) as string | undefined;
  const parentEntityId = (reqRaw.parent_entity_id ?? respRaw.parent_entity_id) as string | undefined;
  const purpose = (reqRaw.purpose ?? respRaw.purpose) as string | undefined;

  const messages = toRecordArray(reqInputs.messages ?? reqRaw.messages);
  const systemPrompt = toString(reqInputs.systemPrompt ?? reqRaw.system_prompt);

  // Brief mode detection
  const isBriefMode = !!(respRaw.messages_hash || respRaw.system_prompt_hash);
  const messagesHash = typeof respRaw.messages_hash === 'string' ? respRaw.messages_hash : undefined;
  const systemPromptHash = typeof respRaw.system_prompt_hash === 'string' ? respRaw.system_prompt_hash : undefined;

  // Response content - try outputs first, then raw
  const responseContent = (respOutputs.content ?? respOutputs.response ?? respOutputs.text) as string | undefined;
  const rawResponse = (respRaw.content ?? respRaw.response ?? respRaw.text) as string | undefined;

  // Decision parsing (tool calls) - try multiple sources
  const parsedResponse = (respOutputs.parsed_response ?? respOutputs.parsedResponse ?? respRaw.parsed_response ?? respRaw.parsedResponse) as Record<string, unknown> | undefined;
  const toolCalls: Array<{ tool: string; arguments: Record<string, unknown>; callId?: string }> = [];

  if (parsedResponse?.tool_calls && Array.isArray(parsedResponse.tool_calls)) {
    for (const tc of parsedResponse.tool_calls) {
      if (typeof tc === 'object' && tc !== null) {
        toolCalls.push({
          tool: String(tc.tool ?? tc.name ?? tc.function?.name ?? 'unknown'),
          arguments: (tc.arguments ?? tc.function?.arguments ?? tc.params ?? {}) as Record<string, unknown>,
          callId: (tc.call_id ?? tc.id) as string | undefined,
        });
      }
    }
  }

  // Tokens (will be populated after backend Stage 1)
  const tokensInRaw = respRaw.tokens_in ?? respOutputs.tokens_in;
  const tokensOutRaw = respRaw.tokens_out ?? respOutputs.tokens_out;
  const tokensIn = toNumber(tokensInRaw);
  const tokensOut = toNumber(tokensOutRaw);

  return {
    kind: 'llm',
    llmCallId: typeof llmCallId === 'string' ? llmCallId : undefined,
    parentEntityType: typeof parentEntityType === 'string' ? parentEntityType : undefined,
    parentEntityId: typeof parentEntityId === 'string' ? parentEntityId : undefined,
    purpose: typeof purpose === 'string' ? purpose : undefined,
    prompt: messages || systemPrompt || messagesHash || systemPromptHash ? {
      messages,
      systemPrompt,
      isBriefMode,
      messagesHash,
      systemPromptHash,
    } : undefined,
    response: responseContent || rawResponse ? {
      content: responseContent,
      rawResponse,
      responseLength: typeof respOutputs.responseLength === 'number'
        ? respOutputs.responseLength
        : (responseContent?.length ?? rawResponse?.length),
    } : undefined,
    decision: toolCalls.length > 0 ? { toolCalls } : undefined,
    params: {
      model: toString(reqInputs.model ?? reqRaw.model),
      temperature: toNumber(reqInputs.temperature ?? reqRaw.temperature),
      maxTokens: toNumber(reqInputs.maxTokens ?? reqInputs.max_tokens ?? reqRaw.max_tokens),
    },
    tokensIn,
    tokensOut,
  };
}

function buildToolData(events: SemanticEvent[]): ToolData {
  const call = events.find(e => e.raw_type === 'operation_call' || e.raw_type === 'tool_call');
  const result = events.find(e => e.raw_type === 'operation_result' || e.raw_type === 'tool_result');
  const retries = events.filter(e => e.raw_type === 'protocol_retry');

  // Try multiple data sources
  const rawCall = call?.raw?.raw ?? {};
  const callInputs = call?.inputs ?? {};
  const rawResult = result?.raw?.raw ?? {};
  const resultOutputs = result?.outputs ?? {};

  // Tool slug can be in various places
  const toolSlug = String(
    callInputs.operation_slug ??
    callInputs.tool ??
    callInputs.operation ??
    rawCall.operation_slug ??
    rawCall.tool ??
    rawCall.operation ??
    'unknown'
  );

  const callId = String(callInputs.call_id ?? rawCall.call_id ?? '');
  const llmCallId = (callInputs.llm_call_id ?? rawCall.llm_call_id ?? resultOutputs.llm_call_id ?? rawResult.llm_call_id) as string | undefined;
  const calledByAgentSlug = (callInputs.agent_slug ?? rawCall.agent_slug ?? resultOutputs.agent_slug ?? rawResult.agent_slug) as string | undefined;
  const calledByAgentRunId = (callInputs.agent_run_id ?? rawCall.agent_run_id ?? resultOutputs.agent_run_id ?? rawResult.agent_run_id) as string | undefined;

  // Arguments can be in inputs or raw
  const args = (callInputs.arguments ?? callInputs.parameters ?? callInputs.input ?? callInputs.payload ??
    rawCall.arguments ?? rawCall.parameters ?? rawCall.input ?? rawCall.payload ?? {}) as Record<string, unknown>;

  // Success can be in outputs or raw
  const success = (resultOutputs.success ?? rawResult.success) === true;

  // Result data
  const resultData = success
    ? (resultOutputs.result ?? resultOutputs.output ?? resultOutputs.data ??
       rawResult.result ?? rawResult.output ?? rawResult.data)
    : undefined;

  // Error message
  const errorMessage = !success
    ? String(resultOutputs.error ?? resultOutputs.message ??
        rawResult.error ?? rawResult.message ?? 'Failed')
    : undefined;
  const errorCodeRaw = resultOutputs.error_code ?? rawResult.error_code;
  const retryableRaw = resultOutputs.retryable ?? rawResult.retryable;

  return {
    kind: 'tool',
    toolSlug,
    callId: callId || undefined,
    llmCallId: typeof llmCallId === 'string' ? llmCallId : undefined,
    calledByAgentSlug: typeof calledByAgentSlug === 'string' ? calledByAgentSlug : undefined,
    calledByAgentRunId: typeof calledByAgentRunId === 'string' ? calledByAgentRunId : undefined,
    arguments: Object.keys(args).length > 0 ? args : undefined,
    result: {
      success,
      data: resultData,
      error: errorMessage,
      errorCode: typeof errorCodeRaw === 'string' ? errorCodeRaw : undefined,
      retryable: typeof retryableRaw === 'boolean' ? retryableRaw : undefined,
    },
    retries: retries.length > 0 ? retries.map((r, i) => ({
      attempt: i + 1,
      error: String(r.decision?.reason ?? r.summary ?? r.outputs?.error ?? r.raw?.raw?.error ?? ''),
    })) : undefined,
  };
}

function buildPlannerData(event: SemanticEvent): PlannerData {
  // Try multiple data sources: raw, decision, inputs, outputs
  const raw = event.raw?.raw ?? {};
  const decision = event.decision ?? {};
  const inputs = event.inputs ?? {};
  const outputs = event.outputs ?? {};

  // kind/action_type can be in raw or decision
  const kind = String(
    raw.kind ??
    raw.action_type ??
    raw.action ??
    decision.kind ??
    decision.action_type ??
    decision.action ??
    'planner_step'
  );

  // rationale can be in raw, decision, or event.summary
  const rationale =
    typeof raw.rationale === 'string' ? raw.rationale :
    typeof decision.rationale === 'string' ? decision.rationale :
    typeof event.summary === 'string' ? event.summary :
    undefined;

  // available agents can be in various places
  const availableAgents =
    raw.available_agents ??
    raw.availableAgents ??
    decision.available_agents ??
    decision.availableAgents ??
    inputs.available_agents ??
    inputs.availableAgents;

  // previous results / facts
  const previousResults =
    raw.previous_results ??
    raw.previousResults ??
    raw.facts ??
    decision.previous_results ??
    decision.previousResults ??
    decision.facts ??
    inputs.previous_results ??
    inputs.previousResults;

  // goal can be in raw, inputs, or decision
  const goal =
    typeof raw.goal === 'string' ? raw.goal :
    typeof inputs.goal === 'string' ? inputs.goal :
    typeof decision.goal === 'string' ? decision.goal :
    undefined;

  // alternatives can be in raw or decision
  const alternatives =
    (raw.alternatives ?? decision.alternatives) as PlannerData['alternatives'] ?? undefined;

  // agent slug for call_agent
  const agentSlug =
    raw.agent_slug ??
    raw.agent ??
    decision.agent_slug ??
    decision.agent ??
    decision.chosenAgentSlug ??
    '';

  // agent input
  const agentInput =
    raw.agent_input ??
    decision.agent_input ??
    decision.agentInput ??
    decision.chosenAgentInput ??
    undefined;

  return {
    kind: 'planner',
    stepKind: kind,
    rationale,
    alternatives,
    inputs: {
      goal,
      availableAgents: Array.isArray(availableAgents) ? availableAgents.map(String) : undefined,
      previousResults: Array.isArray(previousResults) ? previousResults : undefined,
    },
    decision: kind === 'call_agent' || kind.includes('agent') ? {
      chosenAgentSlug: String(agentSlug),
      agentInput: agentInput as Record<string, unknown> ?? undefined,
    } : undefined,
  };
}

function buildAgentData(
  events: SemanticEvent[],
  subAgentRun?: SubAgentRun,
): AgentData {
  // Find agent-identifying events
  const firstPlannerStep = events.find(e =>
    e.raw_type === 'planner_step' &&
    (e.raw?.raw?.kind === 'call_agent' || e.decision?.kind === 'call_agent')
  );

  const rawPlanner = firstPlannerStep?.raw?.raw ?? {};
  const slug = String(rawPlanner.agent_slug ?? rawPlanner.agent ?? 'unknown');

  // Look for partial_mode warning
  const partialModeEvent = events.find(e => e.raw_type === 'partial_mode' || e.raw?.raw?.partial_mode_warning);
  const partialModeWarning = partialModeEvent
    ? String(partialModeEvent.raw?.raw?.warning ?? partialModeEvent.raw?.raw?.partial_mode_warning ?? '')
    : undefined;

  // Look for version info in user_request or elsewhere
  const userRequest = events.find(e => e.raw_type === 'user_request');
  const hasOverrides = !!userRequest?.raw?.raw?.has_overrides;

  // Extract tools available from context snapshot if present
  const contextSnapshot = userRequest?.raw?.raw?.context_snapshot as Record<string, unknown> | undefined;
  const toolsAvailable = Array.isArray(contextSnapshot?.available_operations)
    ? contextSnapshot.available_operations.map(op => typeof op === 'string' ? op : String(op.operation_slug ?? op.tool ?? op))
    : undefined;

  return {
    kind: 'agent',
    slug,
    versionId: subAgentRun ? String(subAgentRun.runId) : undefined,
    versionLabel: subAgentRun ? 'sub-agent' : undefined,
    hasOverrides,
    toolsAvailable,
    partialModeWarning,
    // deniedTools and detailed prompt info require backend Stage 1
  };
}

function buildErrorData(event: SemanticEvent): ErrorData {
  const raw = event.raw?.raw ?? {};
  return {
    kind: 'error',
    code: typeof raw.error_code === 'string' ? raw.error_code : undefined,
    userMessage: String(raw.user_message ?? raw.message ?? raw.error ?? 'Unknown error'),
    operatorMessage: typeof raw.operator_message === 'string' ? raw.operator_message : undefined,
    debug: raw.debug as ErrorData['debug'] ?? undefined,
  };
}

function buildUnknownData(event: SemanticEvent): UnknownData {
  return {
    kind: 'unknown',
    rawType: event.raw_type,
    raw: event.raw?.raw ?? {},
    hint: `Тип "${event.raw_type}" не классифицирован — добавь в normalize.ts и buildEntityTree.ts`,
  };
}

function buildRunData(events: SemanticEvent[]): RunData {
  const userRequest = events.find(e => e.raw_type === 'user_request');
  const budgetPolicy = events.find(e => e.raw_type === 'budget_policy');
  const finalResponse = events.find(e => e.raw_type === 'final_response' || e.raw_type === 'final');
  const error = events.find(e => e.raw_type === 'error' && e.status === 'error');

  const rawBudget = budgetPolicy?.raw?.raw ?? {};

  // Collect routing decisions
  const routingDecisions = events
    .filter(e => e.raw_type === 'routing_decision' || e.raw_type === 'routing')
    .map(e => ({
      agentSlug: typeof e.decision?.agent_slug === 'string' ? e.decision.agent_slug : undefined,
      reason: String(e.summary ?? e.decision?.reason ?? ''),
      timestamp: e.started_at,
    }));

  return {
    kind: 'run',
    userRequest: typeof userRequest?.inputs?.content === 'string'
      ? userRequest.inputs.content
      : String(userRequest?.summary ?? ''),
    agentSlug: typeof userRequest?.raw?.raw?.agent_slug === 'string'
      ? userRequest.raw.raw.agent_slug
      : undefined,
    limits: {
      maxSteps: typeof rawBudget.max_steps === 'number' ? rawBudget.max_steps : undefined,
      maxTools: typeof rawBudget.max_tool_calls_total === 'number' ? rawBudget.max_tool_calls_total : undefined,
      maxWallTimeMs: typeof rawBudget.max_wall_time_ms === 'number' ? rawBudget.max_wall_time_ms : undefined,
      maxRetries: typeof rawBudget.max_retries === 'number' ? rawBudget.max_retries : undefined,
    },
    finalContent: finalResponse?.outputs?.content as string | undefined,
    finalError: error?.status === 'error' ? String(error.summary) : undefined,
    routingDecisions: routingDecisions.length > 0 ? routingDecisions : undefined,
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

export function buildEntityTree(
  events: SemanticEvent[],
  options: BuildEntityTreeOptions = {},
): TraceEntity {
  const { linkSubAgents = false, subAgentRuns = [] } = options;

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

  // Stack tracks current hierarchy path: [root, orchestrator?, agent?, ...]
  const stack: StackItem[] = [{ entity: root, startIndex: 0 }];

  // Track pending pairs (llm_request waiting for llm_response, etc.)
  const pendingPairs: Map<string, PendingPair> = new Map();
  const llmEntityByCallId: Map<string, TraceEntity> = new Map();
  const llmEventsByCallId: Map<string, SemanticEvent[]> = new Map();
  const agentByRunId: Map<string, TraceEntity> = new Map();
  const pendingAgentsBySlug: Map<string, TraceEntity[]> = new Map();

  // Track agent windows (heuristic-based until backend Stage 1)
  let currentAgentWindow: { startIdx: number; events: SemanticEvent[]; plannerStep: SemanticEvent } | null = null;
  const plannerByIteration: Map<string, TraceEntity> = new Map();
  let synthesisEntity: TraceEntity | null = null;

  // Helper: push new entity to current top of stack
  function pushEntity(entity: TraceEntity): void {
    const parent = stack[stack.length - 1];
    entity.parentId = parent.entity.id;
    entity.depth = parent.entity.depth + 1;
    parent.entity.children.push(entity);
    stack.push({ entity, startIndex: events.findIndex(e => e.id === entity.sourceEventIds[0]) });
  }

  // Helper: pop from stack until target depth
  function popToDepth(targetDepth: number): void {
    while (stack.length > targetDepth + 1) {
      const item = stack.pop();
      if (item) {
        // Close entity: compute budget delta, finalize duration
        const endEvent = events[events.length - 1]; // Last event seen so far
        const startEvent = events[item.startIndex];
        if (startEvent?.started_at && endEvent?.started_at) {
          const startMs = new Date(startEvent.started_at).getTime();
          const endMs = new Date(endEvent.started_at).getTime();
          item.entity.durationMs = Math.max(0, endMs - startMs);
        }
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
      id: hashIds([event.id, `planner-${key}`]),
      kind: 'planner',
      parentId: root.id,
      depth: 1,
      children: [],
      title: `Plan #${key || 1}`,
        status: 'info',
        startedAt: event.started_at,
        durationMs: event.duration_ms,
        sourceEventIds: includeEventInContainer ? [event.id] : [],
        budgetSnapshot: budget,
        data: {
          kind: 'planner',
          stepKind: 'iteration',
          rationale: `Planner iteration ${numericIteration || 1}`,
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
      id: hashIds([event.id, 'synthesis']),
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

  function enrichPlannerIterationFromStep(container: TraceEntity, plannerData: PlannerData): void {
    if (container.data.kind !== 'planner') return;
    container.data.stepKind = plannerData.stepKind;
    if (plannerData.rationale) container.data.rationale = plannerData.rationale;
    if (plannerData.decision) container.data.decision = plannerData.decision;
    const label = String((container.data as PlannerData).stepKind ?? 'iteration');
    container.title = `Plan: ${label}`;
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

  // Process each event
  for (let i = 0; i < events.length; i++) {
    const event = events[i];
    const category = event.category;
    const rawType = event.raw_type;
    const rawPayload = (event.raw?.raw ?? {}) as Record<string, unknown>;
    const stage = String(rawPayload.stage ?? '').toLowerCase();
    const eventAgentRunId = typeof rawPayload.agent_run_id === 'string' ? rawPayload.agent_run_id : undefined;

    if (event.phase === 'agent' && eventAgentRunId && currentAgentWindow && stack[stack.length - 1].entity.kind === 'agent') {
      agentByRunId.set(eventAgentRunId, stack[stack.length - 1].entity);
    }
    if (event.phase === 'agent') {
      resolveAgentForEvent(event);
    }

    if ((event.phase === 'planner' || event.phase === 'synthesis') && currentAgentWindow) {
      closeCurrentAgentWindow(event, 'ok');
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
      const slug = String(event.raw?.raw?.slug ?? 'orchestrator');
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
          role: event.raw?.raw?.role as OrchestratorData['role'] ?? undefined,
          intent: typeof event.raw?.raw?.intent === 'string' ? event.raw.raw.intent : undefined,
        },
      };
      pushEntity(orchestrator);
      continue;
    }

    // --- Handle orchestrator_end (backend Stage 1) ---
    if (rawType === 'orchestrator_end') {
      popToDepth(1); // Pop to root level
      continue;
    }

    // --- Handle agent_start (backend Stage 1) ---
    if (rawType === 'agent_start') {
      const slug = String(event.raw?.raw?.slug ?? 'agent');
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
          isBriefMode: false,
        } as AgentData,
      };
      pushEntity(agent);
      continue;
    }

    // --- Handle agent_end (backend Stage 1) ---
    if (rawType === 'agent_end') {
      // Pop until we exit agent level
      while (stack.length > 2 && stack[stack.length - 1].entity.kind === 'agent') {
        stack.pop();
      }
      continue;
    }

    if (event.phase === 'planner' && rawType === 'status' && stage.includes('planner')) {
      ensurePlannerIterationEntity(event);
      continue;
    }

    // --- Handle planner_step ---
    if (rawType === 'planner_step') {
      const plannerData = buildPlannerData(event);
      const plannerContainer = event.phase === 'planner' ? ensurePlannerIterationEntity(event, false) : null;

      if (plannerContainer) {
        // Planner iteration is the business-step container; planner_step is a raw step inside it.
        if (!plannerContainer.sourceEventIds.includes(event.id)) plannerContainer.sourceEventIds.push(event.id);
        const budget = extractBudgetSnapshot(event);
        if (budget) {
          plannerContainer.budgetSnapshot = plannerContainer.budgetSnapshot
            ? mergeBudgetSnapshots(plannerContainer.budgetSnapshot, budget)
            : budget;
        }
        enrichPlannerIterationFromStep(plannerContainer, plannerData);
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
      }

      // --- Heuristic: call_agent starts agent window ---
      if (plannerData.stepKind === 'call_agent' && !currentAgentWindow) {
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
          agentByRunId.set(plannerAgentRunId, agentEntity);
        } else if (agentSlug) {
          queuePendingAgent(agentSlug, agentEntity);
        }
        currentAgentWindow = { startIdx: i, events: [event], plannerStep: event };
      }

      // --- Heuristic: final/abort/ask_user closes agent window ---
      if (['final', 'abort', 'ask_user', 'direct_answer'].includes(plannerData.stepKind)) {
        if (currentAgentWindow) {
          closeCurrentAgentWindow(
            event,
            plannerData.stepKind === 'final'
              ? 'ok'
              : plannerData.stepKind === 'abort'
                ? 'error'
                : 'warn',
          );
        }
      }

      continue;
    }

    // --- Handle final_response: close agent window ---
    if (rawType === 'final_response' || rawType === 'final') {
      if (currentAgentWindow) closeCurrentAgentWindow(event, event.status === 'error' ? 'error' : 'ok');

      if (event.phase === 'synthesis') {
        const synthesisParent = ensureSynthesisEntity(event);
        if (!synthesisParent.sourceEventIds.includes(event.id)) synthesisParent.sourceEventIds.push(event.id);
        synthesisParent.status = event.status;
        if (synthesisParent.data.kind === 'orchestrator') {
          synthesisParent.data.intent = String(event.outputs?.content ?? '');
        }
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
      }
      continue;
    }

    // --- Handle budget_consumed (close agent window if final) ---
    if (rawType === 'budget_consumed') {
      // Check if this is the final budget event (no more events after)
      const isFinalBudget = i === events.length - 1 ||
        events.slice(i + 1).every(e => ['system', 'status'].includes(e.category));

      if (isFinalBudget && currentAgentWindow) {
        closeCurrentAgentWindow(event, 'ok');
      }
    }

    // --- Handle llm_request (start pending pair) ---
    if (rawType === 'llm_request') {
      const llmCallId = getLlmCallId(event);
      pendingPairs.set(llmCallId, { type: 'llm', startEvent: event, events: [event] });
      llmEventsByCallId.set(llmCallId, [event]);
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
          data: buildLLMData(pairEvents),
        };

        const parent = resolveParentForEvent(event);
        llmEntity.parentId = parent.id;
        llmEntity.depth = parent.depth + 1;
        parent.children.push(llmEntity);
        llmEntityByCallId.set(llmCallId, llmEntity);
      }

      if (rawType === 'llm_call') pendingPairs.delete(llmCallId);

      if (currentAgentWindow) {
        currentAgentWindow.events.push(event);
      }
      continue;
    }

    // --- Handle operation_call (start pending tool pair) ---
    if (rawType === 'operation_call' || rawType === 'tool_call') {
      const callId = String(event.raw?.raw?.call_id ?? event.id);
      pendingPairs.set(callId, { type: 'tool', startEvent: event, events: [event] });
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
      const explicitAgent = explicitAgentRunId ? agentByRunId.get(explicitAgentRunId) : undefined;
      if (explicitAgent) {
        toolEntity.parentId = explicitAgent.id;
        toolEntity.depth = explicitAgent.depth + 1;
        explicitAgent.children.push(toolEntity);
      } else {
        const parent = stack[stack.length - 1];
        toolEntity.parentId = parent.entity.id;
        toolEntity.depth = parent.entity.depth + 1;
        parent.entity.children.push(toolEntity);
        if (parent.entity.kind === 'agent' && explicitAgentRunId) {
          agentByRunId.set(explicitAgentRunId, parent.entity);
        } else if (parent.entity.kind === 'agent' && explicitAgentSlug) {
          const parentData = parent.entity.data;
          if (parentData.kind === 'agent' && parentData.slug === explicitAgentSlug && explicitAgentRunId) {
            agentByRunId.set(explicitAgentRunId, parent.entity);
          }
        }
      }

      // Remove from pending
      if (callId) pendingPairs.delete(callId);

      if (currentAgentWindow) {
        currentAgentWindow.events.push(event);
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

      if (currentAgentWindow) {
        currentAgentWindow.events.push(event);
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

      if (currentAgentWindow) {
        currentAgentWindow.events.push(event);
      }
      continue;
    }

    // --- Handle status/system runtime markers via phase-first routing ---
    if (rawType === 'status') {
      if (['planner', 'agent', 'synthesis', 'triage', 'preflight', 'pipeline'].includes(event.phase)) {
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
        if (currentAgentWindow) currentAgentWindow.events.push(event);
        continue;
      }
    }

    // --- Handle unknown / unclassified ---
    if (category === 'system' || !['input', 'budget', 'llm', 'decision', 'retry', 'operation', 'policy', 'planner', 'final', 'error'].includes(category)) {
      if (['planner', 'agent', 'synthesis', 'triage', 'preflight', 'pipeline'].includes(event.phase)) {
        if (currentAgentWindow) currentAgentWindow.events.push(event);
        continue;
      }
      // Skip pure status noise, but capture meaningful system events
      if (['delta', 'thinking', 'waiting_input', 'stop', 'done'].includes(rawType)) {
        // Runtime noise — skip as separate entity, but attach metadata if needed
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

      if (currentAgentWindow) {
        currentAgentWindow.events.push(event);
      }
      continue;
    }

    // --- Default: budget and other events attach to current context ---
    if (currentAgentWindow) {
      currentAgentWindow.events.push(event);
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

  // Compute aggregate budgets bottom-up
  function computeAggregateBudgets(entity: TraceEntity): void {
    for (const child of entity.children) {
      computeAggregateBudgets(child);
    }

    if (entity.children.length === 0) return;

    const childrenSnapshots = entity.children
      .map(c => c.budgetSnapshot)
      .filter((b): b is BudgetSnapshot => !!b);
    const childrenDeltas = entity.children
      .map(c => c.budgetDelta)
      .filter((b): b is BudgetDelta => !!b);

    if (!entity.budgetSnapshot && childrenSnapshots.length > 0) {
      entity.budgetSnapshot = childrenSnapshots.reduce((a, b) => mergeBudgetSnapshots(a, b), {} as BudgetSnapshot);
    }

    if (!entity.budgetDelta && childrenDeltas.length > 0) {
      entity.budgetDelta = childrenDeltas.reduce((a, b) => sumBudgetDeltas(a, b), {} as BudgetDelta);
    }
  }

  computeAggregateBudgets(root);

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
