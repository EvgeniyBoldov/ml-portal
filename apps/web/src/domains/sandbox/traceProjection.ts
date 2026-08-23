import type { RuntimeJournalEvent, SandboxTraceState, TraceEntity } from './traceState';
import { callDisplayName, llmResponseStatus, purposeLabel, toolResult } from './callInspection';

export type TraceCallKind = 'llm' | 'tool' | 'clarify' | 'confirm' | 'error';

export interface TraceCall {
  entity: TraceEntity;
  /** Canonical journal rows owned by this call entity. */
  events: RuntimeJournalEvent[];
  request: RuntimeJournalEvent;
  response?: RuntimeJournalEvent;
  /** Retry rows explicitly correlated with this LLM call id. */
  retryEvents: RuntimeJournalEvent[];
  /** Tool calls explicitly linked to this LLM call through llm_call_id. */
  linkedToolCalls: RuntimeJournalEvent[];
  kind: TraceCallKind;
  title: string;
  summary?: string;
  toolCallCount?: number;
  extraction?: TraceExtraction;
  /** Logical compatibility id for historical retry rows. */
  logicalLlmCallId?: string;
  /** Legacy attempts, present only when historical rows used separate IDs. */
  attempts?: TraceCall[];
}

/** Canonical document-extraction subrun owned by a tool call. */
export interface TraceExtraction {
  entity: TraceEntity;
  events: RuntimeJournalEvent[];
  start?: RuntimeJournalEvent;
  end?: RuntimeJournalEvent;
}

export interface TraceExecutorRun {
  entity: TraceEntity;
  start: RuntimeJournalEvent;
  task: string;
  executorType: string;
  executorName: string;
  executorSlug: string;
  calls: TraceCall[];
  metrics: TraceMetrics;
  memoryResult?: TraceMemoryComponentResult;
  preflight?: TracePreflight;
  prompt?: TracePrompt;
  rbacSnapshot?: unknown;
  limitsSnapshot?: unknown;
}

export interface TracePrompt {
  text?: string;
  hash?: string;
  snapshot?: unknown;
}

export interface TracePreflight {
  status: string;
  mode?: string;
  durationMs?: number;
  missing: {
    tools: string[];
    collections: string[];
    credentials: string[];
  };
  operationsCount?: number;
  dataInstancesCount?: number;
  rbacSnapshot?: unknown;
}

export interface TraceMemoryFact {
  scope: string;
  kind: string;
  subject: string;
  value: string;
  confidence?: number;
  changeType: string;
  statusBefore?: string;
  statusAfter?: string;
  supportBefore?: number;
  supportAfter?: number;
  supportDelta?: number;
  compactionAction?: string;
}

export interface TraceMemoryComponentResult {
  componentName: 'fact_extractor' | 'fact_compactor';
  status: string;
  insertedCount: number;
  updatedCount: number;
  skippedCount: number;
  facts: TraceMemoryFact[];
}

export interface TraceStage {
  entity: TraceEntity;
  start: RuntimeJournalEvent;
  number: number;
  iterationNumber: number;
  stepNumber: number;
  iterationType: string;
  label: string;
  task: string;
  /** All canonical steps in this planner iteration, in execution order. */
  steps: TraceStep[];
  executorRuns: TraceExecutorRun[];
  metrics: TraceMetrics;
}

export interface TraceStep {
  key: string;
  /** Real step entity; synthetic system steps use their owning stage entity. */
  entity: TraceEntity;
  stage: TraceStage;
  number: number;
  taskId?: string;
  title: string;
  objective?: string;
  inputs?: unknown;
  result?: unknown;
  executorRuns: TraceExecutorRun[];
  metrics: TraceMetrics;
}

export type TraceInspectionTarget =
  | { kind: 'iteration'; key: string; stage: TraceStage }
  | { kind: 'step'; key: string; step: TraceStep }
  | { kind: 'executor_run'; key: string; executor: TraceExecutorRun; stage: TraceStage }
  | { kind: 'call'; key: string; call: TraceCall; executor: TraceExecutorRun; stage: TraceStage }
  | { kind: 'error'; key: string; call: TraceCall; executor: TraceExecutorRun; stage: TraceStage };

export interface TraceMetrics {
  elapsedMs?: number;
  tokens?: number;
  retries?: number;
  calls?: number;
  successfulCalls?: number;
  failedCalls?: number;
}

const asString = (value: unknown): string => typeof value === 'string' ? value.trim() : '';
const asNumber = (value: unknown): number | undefined => typeof value === 'number' && Number.isFinite(value) ? value : undefined;
const asRecord = (value: unknown): Record<string, unknown> | undefined => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
);
const isEndEvent = (type: string): boolean => type.endsWith('_end') || type.endsWith('_finished');
const iterationLabel = (type: string, number: number): string => {
  if (type === 'replan') return 'Перепланирование';
  if (type === 'decision') return number > 1 ? 'Перепланирование' : 'Планирование';
  if (type === 'execution') return 'Исполнение';
  if (type === 'synthesis') return 'Подготовка ответа';
  if (type === 'extraction') return 'Извлечение фактов';
  if (type === 'preparation') return 'Подготовка';
  return type || 'Этап';
};
const eventsFor = (state: SandboxTraceState, entity: TraceEntity): RuntimeJournalEvent[] => (
  entity.eventIds.map((id) => state.eventsById[id]).filter((event): event is RuntimeJournalEvent => Boolean(event))
);
const startFor = (state: SandboxTraceState, entity: TraceEntity): RuntimeJournalEvent | undefined => (
  eventsFor(state, entity).find((event) => event.event_type.endsWith('_start') || event.event_type.endsWith('_started'))
);

function memoryComponentResult(events: RuntimeJournalEvent[]): TraceMemoryComponentResult | undefined {
  const resultEvent = [...events].reverse().find((event) => event.event_type === 'memory_component_result');
  if (!resultEvent) return undefined;
  const payload = resultEvent.payload;
  const componentName = asString(payload.component_name);
  if (componentName !== 'fact_extractor' && componentName !== 'fact_compactor') return undefined;
  const sourceFacts = Array.isArray(payload.facts)
    ? payload.facts
    : ([...events].reverse().find((event) => event.event_type === 'memory_facts_result')?.payload.facts ?? []);
  const facts = Array.isArray(sourceFacts) ? sourceFacts.flatMap((item): TraceMemoryFact[] => {
    const fact = asRecord(item);
    if (!fact) return [];
    const subject = asString(fact.subject);
    const value = asString(fact.value);
    if (!subject || !value) return [];
    return [{
      scope: asString(fact.scope) || 'unknown',
      kind: asString(fact.kind) || 'fact',
      subject,
      value,
      confidence: asNumber(fact.confidence),
      changeType: asString(fact.change_type) || (componentName === 'fact_extractor' ? 'candidate_extracted' : 'candidate_reinforced'),
      statusBefore: asString(fact.status_before) || undefined,
      statusAfter: asString(fact.status_after) || asString(fact.status) || undefined,
      supportBefore: asNumber(fact.support_before),
      supportAfter: asNumber(fact.support_after) ?? asNumber(fact.support_count),
      supportDelta: asNumber(fact.support_delta),
      compactionAction: asString(fact.compaction_action) || undefined,
    }];
  }) : [];
  return {
    componentName,
    status: asString(payload.status) || 'completed',
    insertedCount: asNumber(payload.inserted_count) ?? 0,
    updatedCount: asNumber(payload.updated_count) ?? 0,
    skippedCount: asNumber(payload.skipped_count) ?? 0,
    facts,
  };
}

function latestPayload(events: RuntimeJournalEvent[], eventType: string): Record<string, unknown> | undefined {
  return [...events].reverse().find((event) => event.event_type === eventType)?.payload;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];
}

function preflightFor(state: SandboxTraceState, executor: TraceEntity): TracePreflight | undefined {
  const entity = executor.childKeys
    .map((key) => state.entitiesByKey[key])
    .find((child): child is TraceEntity => Boolean(child) && child.type === 'preflight');
  if (!entity) return undefined;
  const events = eventsFor(state, entity);
  const payload = latestPayload(events, 'preflight_completed')
    ?? latestPayload(events, 'preflight_failed')
    ?? latestPayload(events, 'preflight_snapshot')
    ?? latestPayload(events, 'preflight_started')
    ?? {};
  const missing = asRecord(payload.missing) ?? {};
  return {
    status: asString(payload.status) || entity.status || 'unknown',
    mode: asString(payload.mode) || undefined,
    durationMs: asNumber(payload.duration_ms),
    missing: {
      tools: stringArray(missing.tools),
      collections: stringArray(missing.collections),
      credentials: stringArray(missing.credentials),
    },
    operationsCount: asNumber(payload.operations_count),
    dataInstancesCount: asNumber(payload.data_instances_count),
    rbacSnapshot: payload.rbac_audit,
  };
}

function promptFor(events: RuntimeJournalEvent[], calls: TraceCall[]): TracePrompt | undefined {
  const snapshot = [...events].reverse().map((event) => event.payload)
    .map((payload) => payload.config_snapshot ?? payload.context_snapshot)
    .find((value) => {
      const record = asRecord(value) ?? {};
      return record.system_prompt !== undefined || record.system_prompt_hash !== undefined;
    });
  const snapshotRecord = asRecord(snapshot) ?? {};
  const text = asString(snapshotRecord.system_prompt);
  const hash = asString(snapshotRecord.system_prompt_hash);
  if (text || hash || snapshot) return { text: text || undefined, hash: hash || undefined, snapshot };

  for (const call of calls) {
    if (call.kind !== 'llm') continue;
    const messages = Array.isArray(call.request.payload.messages) ? call.request.payload.messages : [];
    const systemMessage = messages.find((message) => {
      const record = asRecord(message) ?? {};
      return record.role === 'system' && typeof record.content === 'string';
    });
    const prompt = asString((asRecord(systemMessage) ?? {}).content);
    if (prompt) return { text: prompt };
  }
  return undefined;
}

function metricsFor(state: SandboxTraceState, entity: TraceEntity): TraceMetrics {
  const events = eventsFor(state, entity);
  const started = startFor(state, entity);
  const ended = events.find((event) => event.event_type.endsWith('_end') || event.event_type.endsWith('_finished'));
  const elapsedMs = ended?.duration_ms ?? (
    started && ended ? new Date(ended.occurred_at).getTime() - new Date(started.occurred_at).getTime() : undefined
  );
  let tokens: number | undefined;
  let retries = 0;
  let calls = 0;
  let successfulCalls = 0;
  let failedCalls = 0;
  for (const event of events) {
    const total = asNumber(event.payload.tokens_total) ?? asNumber(event.payload.tokens);
    if (total !== undefined) tokens = Math.max(tokens ?? 0, total);
    if (event.event_type === 'llm_request' || event.event_type === 'tool_call') calls += 1;
    if (event.event_type === 'llm_response' && llmResponseStatus(event.payload) !== 'error') successfulCalls += 1;
    if (event.event_type === 'tool_result' && event.payload.success === true) successfulCalls += 1;
    if ((event.event_type === 'llm_response' && llmResponseStatus(event.payload) === 'error') || (event.event_type === 'tool_result' && toolResult(event.payload).success === false)) failedCalls += 1;
  }
  const startSequence = events[0]?.sequence ?? -Infinity;
  const endSequence = events[events.length - 1]?.sequence ?? Infinity;
  retries = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .filter((event) => event.event_type === 'protocol_retry' && event.sequence >= startSequence && event.sequence <= endSequence)
    .length;
  return {
    elapsedMs: elapsedMs && elapsedMs > 0 ? elapsedMs : undefined,
    tokens,
    retries: retries || undefined,
    calls: calls || undefined,
    successfulCalls: successfulCalls || undefined,
    failedCalls: failedCalls || undefined,
  };
}

function aggregateMetrics(own: TraceMetrics, children: TraceMetrics[]): TraceMetrics {
  const sum = (key: keyof TraceMetrics): number | undefined => {
    const values = [own, ...children]
      .map((item) => item[key])
      .filter((value): value is number => value !== undefined);
    return values.length ? values.reduce((total, value) => total + value, 0) : undefined;
  };
  const childElapsed = children
    .map((item) => item.elapsedMs)
    .filter((value): value is number => value !== undefined);
  return {
    elapsedMs: own.elapsedMs ?? (childElapsed.length ? childElapsed.reduce((total, value) => total + value, 0) : undefined),
    tokens: sum('tokens'),
    retries: sum('retries'),
    calls: sum('calls'),
    successfulCalls: sum('successfulCalls'),
    failedCalls: sum('failedCalls'),
  };
}

function callFor(state: SandboxTraceState, entity: TraceEntity): TraceCall | null {
  const isLlm = entity.type === 'llm_call';
  const isTool = entity.type === 'tool_call';
  const isInteraction = entity.type === 'question_answer' || entity.type === 'interaction' || entity.type === 'dialog';
  const isError = entity.type === 'error';
  if (!isLlm && !isTool && !isInteraction && !isError) return null;
  const events = eventsFor(state, entity);
  const request = events.find((event) => (
    isLlm ? event.event_type === 'llm_request' :
      isTool ? event.event_type === 'tool_call' :
        isError ? event.event_type === 'error' :
          event.event_type === 'waiting_input' || event.event_type === 'confirmation_required' || event.event_type === 'question_answer'
            || (event.event_type === 'planner_step' && ['clarify', 'ask_user'].includes(asString(event.payload.kind)))
  ));
  if (!request) return null;
  // A retry-chain may intentionally reuse one llm_call entity.  The latest
  // response is the terminal state of that user-visible request; selecting
  // the first response would keep a recovered call red after a retry.
  const response = [...events].reverse().find((event) => (
    isLlm ? event.event_type === 'llm_response' :
      isTool ? event.event_type === 'tool_result' :
        event.event_type === 'question_answer' && event.id !== request.id
  ));
  const interactionKind = request.event_type === 'confirmation_required' ? 'confirm' : 'clarify';
  const toolCallCount = isLlm
    ? Object.values(state.eventsById).filter((event) => (
      event.event_type === 'tool_call'
      && asString(event.payload.llm_call_id) === entity.id
    )).length
    : undefined;
  const logicalLlmCallId = isLlm ? asString(request.payload.logical_llm_call_id) || undefined : undefined;
  const retryEvents = (isLlm || isTool)
    ? state.eventIdsBySequence
      .map((id) => state.eventsById[id])
      .filter((event) => event.event_type === 'protocol_retry'
        && (asString(event.payload.llm_call_id) === entity.id
          || (isTool && asString(event.entity_id ?? event.payload.entity_id) === entity.id)))
    : [];
  const linkedToolCalls = isLlm
    ? Object.values(state.eventsById)
      .filter((event) => event.event_type === 'tool_call'
        && asString(event.payload.llm_call_id) === entity.id)
      .sort((left, right) => left.sequence - right.sequence)
    : [];
  const extractionEntity = isTool
    ? entity.childKeys.map((key) => state.entitiesByKey[key]).find((child): child is TraceEntity => Boolean(child) && child.type === 'extraction')
    : undefined;
  const extraction = extractionEntity ? (() => {
    const extractionEvents = eventsFor(state, extractionEntity);
    return {
      entity: extractionEntity,
      events: extractionEvents,
      start: extractionEvents.find((event) => event.event_type === 'extraction_started'),
      end: [...extractionEvents].reverse().find((event) => event.event_type === 'extraction_completed' || event.event_type === 'extraction_failed'),
    } satisfies TraceExtraction;
  })() : undefined;
  return {
    entity,
    events,
    request,
    response,
    retryEvents,
    linkedToolCalls,
    kind: isLlm ? 'llm' : isTool ? 'tool' : isError ? 'error' : interactionKind,
    title: isLlm
      ? (asString(request.payload.purpose) ? purposeLabel(request.payload.purpose) : asString(request.payload.model) || 'LLM')
      : isTool
        ? callDisplayName(asString(request.payload.tool) || 'Tool')
        : isError
          ? asString(request.payload.error) || asString(request.payload.message) || 'Ошибка'
          : asString(request.payload.question)
            || asString(request.payload.message)
            || asString(request.payload.summary)
            || asString(request.payload.operation)
            || asString(request.payload.tool_slug)
            || (interactionKind === 'confirm' ? 'Подтверждение операции' : 'Уточнение'),
    summary: isTool && response
      ? (() => {
          const result = toolResult(response.payload);
          if (result.message) return result.message;
          const data = result.data && typeof result.data === 'object' ? result.data as Record<string, unknown> : null;
          if (typeof data?.total === 'number') return `${data.total} результатов`;
          if (typeof data?.field_count === 'number') return `Полей: ${data.field_count}`;
          return undefined;
        })()
      : undefined,
    toolCallCount,
    extraction,
    logicalLlmCallId,
  };
}

/**
 * Collapse only historical retry chains that the runtime explicitly
 * correlated. Current runtime retries already share one llm_call entity.
 */
function groupLogicalLlmCalls(calls: TraceCall[]): TraceCall[] {
  const groups = new Map<string, TraceCall[]>();
  const ordered: Array<TraceCall | string> = [];
  for (const call of calls) {
    if (call.kind !== 'llm' || !call.logicalLlmCallId) {
      ordered.push(call);
      continue;
    }
    const existing = groups.get(call.logicalLlmCallId);
    if (existing) {
      existing.push(call);
    } else {
      groups.set(call.logicalLlmCallId, [call]);
      ordered.push(call.logicalLlmCallId);
    }
  }
  return ordered.map((item) => {
    if (typeof item !== 'string') return item;
    const attempts = groups.get(item) ?? [];
    if (attempts.length <= 1) return attempts[0];
    const last = attempts[attempts.length - 1];
    const events = attempts.flatMap((attempt) => attempt.events);
    const retryEvents = attempts.flatMap((attempt) => attempt.retryEvents);
    const linkedToolCalls = attempts.flatMap((attempt) => attempt.linkedToolCalls);
    return {
      ...last,
      entity: attempts[0].entity,
      events,
      request: attempts[0].request,
      response: last.response,
      retryEvents,
      linkedToolCalls,
      toolCallCount: linkedToolCalls.length,
      attempts,
    } satisfies TraceCall;
  });
}

function syntheticCallEntity(event: RuntimeJournalEvent, type?: 'question_answer' | 'error'): TraceEntity {
  const entityType = asString(event.entity_type) || type || 'question_answer';
  const entityId = asString(event.entity_id) || event.id;
  return {
    key: `${entityType}:${entityId}`,
    type: entityType,
    id: entityId,
    parentKey: event.parent_entity_type && event.parent_entity_id
      ? `${event.parent_entity_type}:${event.parent_entity_id}`
      : null,
    childKeys: [],
    eventIds: [event.id],
    status: entityType === 'error' ? 'error' : 'waiting',
    snapshotsByKind: {},
  };
}

function directCallsFor(
  state: SandboxTraceState,
  executor: TraceEntity,
  iteration: TraceEntity,
  excludedEventIds: Set<string>,
): TraceCall[] {
  const executorEvents = eventsFor(state, executor);
  const startSequence = executorEvents.find((item) => item.event_type.endsWith('_start') || item.event_type.endsWith('_started'))?.sequence ?? -Infinity;
  const endSequence = executorEvents
    .filter((item) => isEndEvent(item.event_type))
    .map((item) => item.sequence)
    .sort((left, right) => left - right)[0];
  const events = Object.values(state.eventsById).filter((event) => {
    const parentId = asString(event.parent_entity_id ?? event.payload.parent_entity_id);
    const parentType = asString(event.parent_entity_type ?? event.payload.parent_entity_type);
    const belongsToExecutor = parentType === executor.type && parentId === executor.id;
    const hasNoParent = !parentType && !parentId;
    const isUnscopedCall = event.event_type === 'confirmation_required' || event.event_type === 'error';
    const belongsToActiveExecutor = hasNoParent
      && isUnscopedCall
      && event.sequence >= startSequence
      && (endSequence === undefined || event.sequence <= endSequence);
    const belongsToPlannerIteration = executor.id && executor.type === 'agent_execution'
      && asString(state.entitiesByKey[executor.parentKey ?? '']?.type) === 'planner_iteration'
      && parentType === iteration.type && parentId === iteration.id;
    return belongsToExecutor || belongsToActiveExecutor || belongsToPlannerIteration;
  });

  return events
    .filter((event) => event.event_type === 'llm_request'
      || event.event_type === 'tool_call'
      || event.event_type === 'waiting_input'
      || event.event_type === 'confirmation_required'
      || event.event_type === 'error'
      || (event.event_type === 'planner_step' && ['clarify', 'ask_user'].includes(asString(event.payload.kind))))
    .filter((event) => !excludedEventIds.has(event.id))
    .map((event) => {
      const existing = event.entity_type && event.entity_id
        ? state.entitiesByKey[`${event.entity_type}:${event.entity_id}`]
        : undefined;
      return callFor(state, existing ?? {
        ...syntheticCallEntity(event, event.event_type === 'error' ? 'error' : 'question_answer'),
        parentKey: executor.key,
      });
    })
    .filter((call): call is TraceCall => Boolean(call));
}

function executorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  if (entity.type !== 'agent_execution') return null;
  const start = startFor(state, entity);
  if (!start) return null;
  const payload = start.payload;
  const slug = asString(payload.agent_slug) || 'unknown';
  const executorType = (asString(payload.executor_type) || asString(payload.role) || 'agent').toUpperCase();
  const executorName = asString(payload.executor_name) || (slug === 'planner' ? 'Планер' : slug);
  const task = asString(payload.task_title) || asString(payload.task_objective) || 'Выполнение задачи';
  const childCalls = entity.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((child): child is TraceEntity => Boolean(child))
    .map((child) => callFor(state, child))
    .filter((call): call is TraceCall => Boolean(call));
  const childEventIds = new Set(entity.childKeys.flatMap((key) => state.entitiesByKey[key]?.eventIds ?? []));
  const iteration = entity.parentKey ? state.entitiesByKey[entity.parentKey] : undefined;
  const directCalls = iteration
    ? directCallsFor(state, entity, iteration, childEventIds)
    : directCallsFor(state, entity, entity, childEventIds);
  const calls = groupLogicalLlmCalls([...childCalls, ...directCalls]
    .sort((left, right) => left.request.sequence - right.request.sequence));
  const executorEvents = eventsFor(state, entity);
  const baseMetrics = metricsFor(state, entity);
  const callMetrics = calls.reduce((result, call) => {
    const failed = call.kind === 'error'
      || (call.kind === 'llm' && call.response && llmResponseStatus(call.response.payload) === 'error')
      || (call.kind === 'tool' && call.response && toolResult(call.response.payload).success === false);
    return {
      calls: result.calls + 1,
      successfulCalls: result.successfulCalls + (call.response && !failed ? 1 : 0),
      failedCalls: result.failedCalls + (failed ? 1 : 0),
    };
  }, { calls: 0, successfulCalls: 0, failedCalls: 0 });
  const terminalSequence = entity.eventIds
    .map((id) => state.eventsById[id]?.sequence ?? 0)
    .reduce((max, sequence) => Math.max(max, sequence), start.sequence);
  const nextExecutorSequence = iteration?.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((candidate): candidate is TraceEntity => Boolean(candidate) && candidate.key !== entity.key)
    .map((candidate) => startFor(state, candidate)?.sequence ?? Infinity)
    .filter((sequence) => sequence > start.sequence)
    .sort((left, right) => left - right)[0] ?? Infinity;
  const retryEndSequence = Math.min(
    terminalSequence > start.sequence ? terminalSequence : state.nextSequence ?? terminalSequence,
    nextExecutorSequence - 1,
  );
  const retriesAfterStart = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .filter((event) => event.event_type === 'protocol_retry' && event.sequence >= start.sequence && event.sequence <= retryEndSequence)
    .length;
  return {
    entity,
    start,
    task,
    executorType,
    executorName,
    executorSlug: slug,
    calls,
    metrics: {
      ...baseMetrics,
      retries: retriesAfterStart || baseMetrics.retries,
      calls: callMetrics.calls || baseMetrics.calls,
      successfulCalls: callMetrics.successfulCalls || baseMetrics.successfulCalls,
      failedCalls: callMetrics.failedCalls || baseMetrics.failedCalls,
    },
    memoryResult: memoryComponentResult(executorEvents),
    preflight: preflightFor(state, entity),
    prompt: promptFor(executorEvents, calls),
    rbacSnapshot: latestPayload(executorEvents, 'rbac_snapshot')?.rbac,
    limitsSnapshot: latestPayload(executorEvents, 'budget_snapshot') ?? latestPayload(executorEvents, 'limits_snapshot'),
  };
}

function synthesizerExecutorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  if (entity.type !== 'synthesis_run') return null;
  const start = startFor(state, entity);
  if (!start) return null;
  const calls = groupLogicalLlmCalls(entity.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((child): child is TraceEntity => Boolean(child))
    .map((child) => callFor(state, child))
    .filter((call): call is TraceCall => Boolean(call)));
  return {
    entity,
    start,
    task: 'Подготовка финального ответа',
    executorType: 'SYNTHESIZER',
    executorName: 'Синтезатор',
    executorSlug: 'synthesizer',
    calls,
    metrics: metricsFor(state, entity),
    prompt: promptFor(eventsFor(state, entity), calls),
  };
}

export function projectTraceStages(state: SandboxTraceState): TraceStage[] {
  const plannerStages = Object.values(state.entitiesByKey)
    .filter((entity) => entity.type === 'planner_iteration')
    .map((entity): TraceStage | null => {
      const start = startFor(state, entity);
      if (!start) return null;
      const number = asNumber(start.payload.iteration_number) ?? asNumber(start.payload.iteration) ?? 0;
      const directChildren = entity.childKeys
        .map((key) => state.entitiesByKey[key])
        .filter((child): child is TraceEntity => Boolean(child));
      const stepEntities = directChildren
        .filter((child) => child.type === 'step')
        .sort((left, right) => (startFor(state, left)?.sequence ?? 0) - (startFor(state, right)?.sequence ?? 0));
      const executorRunsByStep = stepEntities.map((stepEntity) => (
        stepEntity.childKeys
          .map((key) => state.entitiesByKey[key])
          .filter((child): child is TraceEntity => Boolean(child))
          .map((child) => executorFor(state, child))
          .filter((executor): executor is TraceExecutorRun => Boolean(executor))
      ));
      const executorRuns = executorRunsByStep.flat();
      const iterationType = asString(start.payload.iteration_type)
        || (executorRuns.some((executor) => executor.executorSlug === 'planner') ? 'decision' : 'execution');
      const task = iterationType === 'replan'
        ? 'Корректировка плана'
        : executorRuns.map((executor) => executor.task).find(Boolean)
        || asString(start.payload.task_title)
        || asString(start.payload.goal)
        || 'Выполнение задачи';
      const stage: TraceStage = {
        entity,
        start,
        number,
        iterationNumber: number,
        stepNumber: 0,
        iterationType,
        label: iterationLabel(iterationType, number),
        task,
        steps: [],
        executorRuns,
        metrics: aggregateMetrics(metricsFor(state, entity), executorRuns.map((executor) => executor.metrics)),
      };
      stage.steps = stepEntities.map((stepEntity, index) => {
        const stepStart = startFor(state, stepEntity);
        const payload = stepStart?.payload ?? {};
        const stepExecutors = executorRunsByStep[index];
        const executor = stepExecutors[0];
        return {
          key: stepEntity.key,
          entity: stepEntity,
          stage,
          number: asNumber(payload.step_number) ?? index + 1,
          taskId: asString(payload.task_id) || asString(payload.phase_id) || undefined,
          title: asString(payload.title) || asString(payload.task_title) || asString(payload.task_objective) || executor?.task || stage.task,
          objective: asString(payload.objective) || asString(payload.task_objective) || undefined,
          inputs: payload.inputs ?? payload.task_inputs,
          executorRuns: stepExecutors,
          metrics: aggregateMetrics(metricsFor(state, stepEntity), stepExecutors.map((executor) => executor.metrics)),
        };
      });
      stage.stepNumber = stage.steps[0]?.number ?? 0;
      return stage;
    })
    .filter((stage): stage is TraceStage => stage !== null)
    .sort((left, right) => left.start.sequence - right.start.sequence);
  const systemStages = Object.values(state.entitiesByKey)
    .filter((entity) => entity.type === 'orchestrator' || entity.type === 'synthesis_run')
    .map((entity): TraceStage | null => {
      const start = startFor(state, entity);
      if (!start) return null;
      const isMemory = entity.type === 'orchestrator' && asString(start.payload.role) === 'memory';
      const isMemoryPreparation = entity.type === 'orchestrator' && asString(start.payload.role) === 'memory_preparation';
      const isSynthesis = entity.type === 'synthesis_run';
      if (!isMemory && !isMemoryPreparation && !isSynthesis) return null;
      const executorRuns = isSynthesis
        ? [synthesizerExecutorFor(state, entity)].filter((executor): executor is TraceExecutorRun => Boolean(executor))
        : entity.childKeys
          .map((key) => state.entitiesByKey[key])
          .filter((child): child is TraceEntity => Boolean(child))
          .map((child) => executorFor(state, child))
          .filter((executor): executor is TraceExecutorRun => Boolean(executor));
      const stage: TraceStage = {
        entity, start, number: plannerStages.length + 1, iterationNumber: plannerStages.length + 1,
        stepNumber: 0, iterationType: isSynthesis ? 'synthesis' : 'memory',
        label: isSynthesis ? 'Подготовка ответа' : isMemoryPreparation ? 'Подготовка памяти' : 'Сохранение памяти',
        task: isSynthesis ? 'Подготовка финального ответа' : isMemoryPreparation ? 'Отбор контекста для планера' : 'Сохранение фактов и сводки', steps: [], executorRuns,
        metrics: aggregateMetrics(metricsFor(state, entity), executorRuns.map((executor) => executor.metrics)),
      };
      if (isMemory || isMemoryPreparation) {
        stage.steps = executorRuns.map((executor, index) => ({
          key: `${entity.key}:memory-step:${executor.entity.id}`,
          entity: executor.entity,
          stage,
          number: index + 1,
          title: executor.executorSlug === 'fact_extractor' ? 'Извлечение фактов'
            : executor.executorSlug === 'fact_compactor' ? 'Компактация фактов'
              : 'Подготовка memory context',
          objective: executor.task,
          executorRuns: [executor],
          metrics: executor.metrics,
        }));
        stage.stepNumber = stage.steps[0]?.number ?? 0;
      }
      return stage;
    })
    .filter((stage): stage is TraceStage => stage !== null);
  return [...plannerStages, ...systemStages].sort((left, right) => left.start.sequence - right.start.sequence);
}

export function stepFor(stage: TraceStage): TraceStep {
  const firstStep = stage.steps[0];
  if (firstStep) return firstStep;
  const executor = stage.executorRuns[0];
  const payload = executor?.start.payload ?? stage.start.payload;
  return {
    key: `step:${stage.entity.key}`,
    entity: stage.entity,
    stage,
    number: stage.stepNumber,
    taskId: asString(payload.task_id) || asString(payload.phase_id) || undefined,
    title: asString(payload.title) || asString(payload.task_title) || asString(payload.task_objective) || stage.task,
    objective: asString(payload.objective) || asString(payload.task_objective) || undefined,
    inputs: payload.inputs ?? payload.task_inputs,
    executorRuns: stage.executorRuns,
    metrics: aggregateMetrics(metricsFor(state, stage.entity), stage.executorRuns.map((executor) => executor.metrics)),
  };
}

/** Resolve a stable inspector selection against the latest normalized trace. */
export function resolveTraceInspectionTarget(
  state: SandboxTraceState,
  key: string,
): TraceInspectionTarget | null {
  for (const stage of projectTraceStages(state)) {
    if (stage.entity.key === key) return { kind: 'iteration', key, stage };
    for (const step of stage.steps.length > 0 ? stage.steps : [stepFor(stage)]) {
      if (step.key === key) return { kind: 'step', key, step };
    }
    for (const executor of stage.executorRuns) {
      if (executor.entity.key === key) return { kind: 'executor_run', key, executor, stage };
      for (const call of executor.calls) {
        if (call.entity.key === key) {
          return call.kind === 'error'
            ? { kind: 'error', key, call, executor, stage }
            : { kind: 'call', key, call, executor, stage };
        }
      }
    }
  }
  return null;
}

export function traceElapsedMs(state: SandboxTraceState, now: number): number | undefined {
  const events = state.eventIdsBySequence.map((id) => state.eventsById[id]).filter(Boolean);
  if (events.length === 0) return undefined;
  const start = new Date(events[0].occurred_at).getTime();
  const terminal = [...events].reverse().find((event) => event.event_type === 'run_end');
  const finish = terminal ? new Date(terminal.occurred_at).getTime() : now;
  return finish > start ? finish - start : undefined;
}
