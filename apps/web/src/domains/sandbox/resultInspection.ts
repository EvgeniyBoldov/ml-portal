import type { SandboxTraceState } from './traceState';
import type { TraceExecutorRun, TraceStage } from './traceProjection';
import { parseCallContent, sanitizeDisplay } from './callInspection';

export type ResultStatus = 'running' | 'completed' | 'failed' | 'unfulfillable' | 'aborted' | 'paused' | 'waiting' | 'unknown';

export type ExecutorResultViewModel = {
  name: string;
  status: ResultStatus;
  statusLabel: string;
  output?: unknown;
  message?: string;
  completionKind?: string;
  sufficientForPhase?: boolean;
  missingInputs?: unknown;
  needs?: unknown;
  artifacts?: unknown;
  operations: { total: number; succeeded: number; failed: number };
};

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
);

const statusOf = (value: unknown): ResultStatus => {
  const status = String(value ?? '').toLowerCase();
  if (['completed', 'success', 'succeeded'].includes(status)) return 'completed';
  if (['failed', 'error'].includes(status)) return 'failed';
  if (status === 'unfulfillable') return 'unfulfillable';
  if (['aborted', 'cancelled', 'canceled'].includes(status)) return 'aborted';
  if (['paused'].includes(status)) return 'paused';
  if (['waiting', 'waiting_input'].includes(status)) return 'waiting';
  return status ? 'running' : 'unknown';
};

export function resultStatusLabel(status: ResultStatus): string {
  return ({
    completed: 'Готово', failed: 'Ошибка', unfulfillable: 'Неисполнимо', aborted: 'Прервано', paused: 'На паузе',
    waiting: 'Ожидает данных', running: 'Выполняется', unknown: 'Нет результата',
  } as Record<ResultStatus, string>)[status];
}

function outputFrom(payload: Record<string, unknown>): unknown {
  for (const key of ['output', 'result', 'answer', 'response', 'content', 'summary', 'message']) {
    if (payload[key] !== undefined && payload[key] !== null && payload[key] !== '') return payload[key];
  }
  return undefined;
}

function errorMessage(payload: Record<string, unknown>): string | undefined {
  for (const key of ['user_message', 'safe_message', 'operator_message', 'message', 'error']) {
    if (typeof payload[key] === 'string' && payload[key].trim()) return payload[key].trim();
  }
  return undefined;
}

export function projectExecutorResult(executor: TraceExecutorRun, trace: SandboxTraceState | null): ExecutorResultViewModel {
  const events = executor.entity.eventIds.map((id) => trace?.eventsById[id]).filter(Boolean);
  const isSynthesizer = executor.executorSlug === 'synthesizer';
  const ended = [...events].reverse().find((event) => event?.event_type === 'agent_end');
  const final = isSynthesizer
    ? Object.values(trace?.eventsById ?? {}).filter((event) => (
      event.event_type === 'final_answer_marker'
      && event.parent_entity_type === 'synthesis_run'
      && event.parent_entity_id === executor.entity.id
    )).sort((left, right) => right.sequence - left.sequence)[0]
    : undefined;
  const error = Object.values(trace?.eventsById ?? {}).find((event) => event.event_type === 'error' && (
    event.payload.agent_execution_id === executor.entity.id
    || (event.parent_entity_type === executor.entity.type && event.parent_entity_id === executor.entity.id)
  ));
  const endPayload = asRecord(ended?.payload);
  const finalPayload = asRecord(final?.payload);
  const errorPayload = asRecord(error?.payload);
  const toolCalls = executor.calls.filter((call) => call.kind === 'tool');
  const succeeded = toolCalls.filter((call) => call.response?.payload.success === true || asRecord(call.response?.payload.result).success === true).length;
  const failed = toolCalls.filter((call) => call.response?.payload.success === false || asRecord(call.response?.payload.result).success === false).length;
  const resultPayload = isSynthesizer && Object.keys(finalPayload).length ? finalPayload : endPayload;
  const status = statusOf(resultPayload.status ?? (error ? 'failed' : executor.entity.status));
  const output = outputFrom(resultPayload);
  return {
    name: executor.executorName,
    status,
    statusLabel: resultStatusLabel(status),
    output: output === undefined ? undefined : sanitizeDisplay(parseCallContent(output).data ?? output),
    message: errorMessage(errorPayload) ?? errorMessage(resultPayload),
    completionKind: typeof endPayload.completion_kind === 'string' ? endPayload.completion_kind : undefined,
    sufficientForPhase: typeof endPayload.sufficient_for_phase === 'boolean' ? endPayload.sufficient_for_phase : undefined,
    missingInputs: endPayload.missing_inputs,
    needs: endPayload.needs,
    artifacts: endPayload.artifacts ?? endPayload.attachments ?? resultPayload.attachments ?? resultPayload.artifacts,
    operations: { total: toolCalls.length, succeeded, failed },
  };
}

export function projectStageResults(stage: TraceStage, trace: SandboxTraceState | null): ExecutorResultViewModel[] {
  return stage.executorRuns.map((executor) => projectExecutorResult(executor, trace));
}
