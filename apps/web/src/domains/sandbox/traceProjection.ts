import type { RuntimeJournalEvent, SandboxTraceState, TraceEntity } from './traceState';
import { callDisplayName, purposeLabel, toolResult } from './callInspection';

export type TraceCallKind = 'llm' | 'tool' | 'clarify' | 'confirm' | 'error';

export interface TraceCall {
  entity: TraceEntity;
  request: RuntimeJournalEvent;
  response?: RuntimeJournalEvent;
  kind: TraceCallKind;
  title: string;
  summary?: string;
  toolCallCount?: number;
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
  stage: TraceStage;
  number: number;
  taskId?: string;
  title: string;
  objective?: string;
  inputs?: unknown;
  result?: unknown;
  executorRuns: TraceExecutorRun[];
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
  const toolCallCount = isLlm
    ? Object.values(state.eventsById).filter((event) => (
      event.event_type === 'tool_call'
      && asString(event.payload.llm_call_id) === entity.id
    )).length
    : undefined;
  return {
    entity,
    request,
    response,
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
  };
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
  const calls = [...childCalls, ...directCalls].sort((left, right) => left.request.sequence - right.request.sequence);
  return { entity, start, task, executorType, executorName, executorSlug: slug, calls, metrics: metricsFor(state, entity) };
}

function synthesizerExecutorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  if (entity.type !== 'synthesis_run') return null;
  const start = startFor(state, entity);
  if (!start) return null;
  const calls = entity.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((child): child is TraceEntity => Boolean(child))
    .map((child) => callFor(state, child))
    .filter((call): call is TraceCall => Boolean(call));
  return {
    entity,
    start,
    task: 'Подготовка финального ответа',
    executorType: 'SYNTHESIZER',
    executorName: 'Синтезатор',
    executorSlug: 'synthesizer',
    calls,
    metrics: metricsFor(state, entity),
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
        metrics: metricsFor(state, entity),
      };
      stage.steps = stepEntities.map((stepEntity, index) => {
        const stepStart = startFor(state, stepEntity);
        const payload = stepStart?.payload ?? {};
        const stepExecutors = executorRunsByStep[index];
        const executor = stepExecutors[0];
        return {
          key: stepEntity.key,
          stage,
          number: asNumber(payload.step_number) ?? index + 1,
          taskId: asString(payload.task_id) || asString(payload.phase_id) || undefined,
          title: asString(payload.title) || asString(payload.task_title) || asString(payload.task_objective) || executor?.task || stage.task,
          objective: asString(payload.objective) || asString(payload.task_objective) || undefined,
          inputs: payload.inputs ?? payload.task_inputs,
          executorRuns: stepExecutors,
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
      const isSynthesis = entity.type === 'synthesis_run';
      if (!isMemory && !isSynthesis) return null;
      const executorRuns = isSynthesis
        ? [synthesizerExecutorFor(state, entity)].filter((executor): executor is TraceExecutorRun => Boolean(executor))
        : entity.childKeys
          .map((key) => state.entitiesByKey[key])
          .filter((child): child is TraceEntity => Boolean(child))
          .map((child) => executorFor(state, child))
          .filter((executor): executor is TraceExecutorRun => Boolean(executor));
      return {
        entity, start, number: plannerStages.length + 1, iterationNumber: plannerStages.length + 1,
        stepNumber: 0, iterationType: isSynthesis ? 'synthesis' : 'preparation',
        label: isSynthesis ? 'Подготовка ответа' : 'Сохранение памяти',
        task: isSynthesis ? 'Подготовка финального ответа' : 'Сохранение фактов и сводки', steps: [], executorRuns,
        metrics: metricsFor(state, entity),
      } satisfies TraceStage;
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
    stage,
    number: stage.stepNumber,
    taskId: asString(payload.task_id) || asString(payload.phase_id) || undefined,
    title: asString(payload.title) || asString(payload.task_title) || asString(payload.task_objective) || stage.task,
    objective: asString(payload.objective) || asString(payload.task_objective) || undefined,
    inputs: payload.inputs ?? payload.task_inputs,
    executorRuns: stage.executorRuns,
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
