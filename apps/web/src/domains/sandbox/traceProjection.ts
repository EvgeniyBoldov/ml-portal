import type { RuntimeJournalEvent, SandboxTraceState, TraceEntity } from './traceState';

export type TraceCallKind = 'llm' | 'tool' | 'clarify' | 'confirm' | 'error';

export interface TraceCall {
  entity: TraceEntity;
  request: RuntimeJournalEvent;
  response?: RuntimeJournalEvent;
  kind: TraceCallKind;
  title: string;
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
}

export interface TraceStage {
  entity: TraceEntity;
  start: RuntimeJournalEvent;
  number: number;
  iterationType: string;
  label: string;
  task: string;
  executorRuns: TraceExecutorRun[];
  metrics: TraceMetrics;
}

export interface TraceStep {
  key: string;
  stage: TraceStage;
  taskId?: string;
  title: string;
  objective?: string;
  inputs?: unknown;
  result?: unknown;
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
}

const asString = (value: unknown): string => typeof value === 'string' ? value.trim() : '';
const asNumber = (value: unknown): number | undefined => typeof value === 'number' && Number.isFinite(value) ? value : undefined;
const isEndEvent = (type: string): boolean => type.endsWith('_end') || type.endsWith('_finished');
const iterationLabel = (type: string, number: number): string => {
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

function metricsFor(state: SandboxTraceState, entity: TraceEntity): TraceMetrics {
  const events = eventsFor(state, entity);
  const started = startFor(state, entity);
  const ended = events.find((event) => event.event_type.endsWith('_end') || event.event_type.endsWith('_finished'));
  const elapsedMs = ended?.duration_ms ?? (
    started && ended ? new Date(ended.occurred_at).getTime() - new Date(started.occurred_at).getTime() : undefined
  );
  let tokens: number | undefined;
  let retries = 0;
  for (const event of events) {
    const total = asNumber(event.payload.tokens_total) ?? asNumber(event.payload.tokens);
    if (total !== undefined) tokens = Math.max(tokens ?? 0, total);
    if (event.event_type === 'protocol_retry') retries += 1;
  }
  return { elapsedMs: elapsedMs && elapsedMs > 0 ? elapsedMs : undefined, tokens, retries: retries || undefined };
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
  const response = events.find((event) => (
    isLlm ? event.event_type === 'llm_response' :
      isTool ? event.event_type === 'tool_result' :
        event.event_type === 'question_answer' && event.id !== request.id
  ));
  const interactionKind = request.event_type === 'confirmation_required' ? 'confirm' : 'clarify';
  return {
    entity,
    request,
    response,
    kind: isLlm ? 'llm' : isTool ? 'tool' : isError ? 'error' : interactionKind,
    title: isLlm
      ? asString(request.payload.model) || 'LLM'
      : isTool
        ? asString(request.payload.tool) || 'Tool'
        : isError
          ? asString(request.payload.error) || asString(request.payload.message) || 'Ошибка'
          : asString(request.payload.question)
            || asString(request.payload.message)
            || asString(request.payload.summary)
            || asString(request.payload.operation)
            || asString(request.payload.tool_slug)
            || (interactionKind === 'confirm' ? 'Подтверждение операции' : 'Уточнение'),
  };
}

function syntheticCallEntity(event: RuntimeJournalEvent, type: 'question_answer' | 'error'): TraceEntity {
  return {
    key: `${type}:${event.id}`,
    type,
    id: event.id,
    parentKey: null,
    childKeys: [],
    eventIds: [event.id],
    status: type === 'error' ? 'error' : 'waiting',
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
    const belongsToPlannerIteration = executor.id && executor.type === 'agent_run'
      && asString(state.entitiesByKey[executor.parentKey ?? '']?.type) === 'planner_iteration'
      && parentType === iteration.type && parentId === iteration.id;
    return belongsToExecutor || belongsToActiveExecutor || belongsToPlannerIteration;
  });

  return events
    .filter((event) => event.event_type === 'waiting_input'
      || event.event_type === 'confirmation_required'
      || event.event_type === 'error'
      || (event.event_type === 'planner_step' && ['clarify', 'ask_user'].includes(asString(event.payload.kind))))
    .filter((event) => !excludedEventIds.has(event.id))
    .map((event) => callFor(state, {
      ...syntheticCallEntity(event, event.event_type === 'error' ? 'error' : 'question_answer'),
      parentKey: executor.key,
    }))
    .filter((call): call is TraceCall => Boolean(call));
}

function executorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  if (entity.type !== 'agent_run') return null;
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
  const calls = [...childCalls, ...directCalls].sort((left, right) => left.request.sequence - right.request.sequence);
  return { entity, start, task, executorType, executorName, executorSlug: slug, calls, metrics: metricsFor(state, entity) };
}

export function projectTraceStages(state: SandboxTraceState): TraceStage[] {
  return Object.values(state.entitiesByKey)
    .filter((entity) => entity.type === 'planner_iteration')
    .map((entity) => {
      const start = startFor(state, entity);
      if (!start) return null;
      const number = asNumber(start.payload.iteration) ?? 0;
      const executorRuns = entity.childKeys
        .map((key) => state.entitiesByKey[key])
        .filter((child): child is TraceEntity => Boolean(child))
        .map((child) => executorFor(state, child))
        .filter((executor): executor is TraceExecutorRun => Boolean(executor));
      const iterationType = asString(start.payload.iteration_type)
        || (executorRuns.some((executor) => executor.executorSlug === 'planner') ? 'decision' : 'execution');
      const task = executorRuns.map((executor) => executor.task).find(Boolean)
        || asString(start.payload.task_title)
        || asString(start.payload.goal)
        || 'Выполнение задачи';
      return {
        entity,
        start,
        number,
        iterationType,
        label: iterationLabel(iterationType, number),
        task,
        executorRuns,
        metrics: metricsFor(state, entity),
      };
    })
    .filter((stage): stage is TraceStage => Boolean(stage))
    .sort((left, right) => left.start.sequence - right.start.sequence);
}

export function stepFor(stage: TraceStage): TraceStep {
  const executor = stage.executorRuns[0];
  const payload = executor?.start.payload ?? stage.start.payload;
  return {
    key: `step:${stage.entity.key}`,
    stage,
    taskId: asString(payload.task_id) || undefined,
    title: asString(payload.task_title) || asString(payload.task_objective) || stage.task,
    objective: asString(payload.task_objective) || undefined,
    inputs: payload.task_inputs,
  };
}

export function traceElapsedMs(state: SandboxTraceState, now: number): number | undefined {
  const events = state.eventIdsBySequence.map((id) => state.eventsById[id]).filter(Boolean);
  if (events.length === 0) return undefined;
  const start = new Date(events[0].occurred_at).getTime();
  const terminal = [...events].reverse().find((event) => event.event_type === 'run_end');
  const finish = terminal ? new Date(terminal.occurred_at).getTime() : now;
  return finish > start ? finish - start : undefined;
}
