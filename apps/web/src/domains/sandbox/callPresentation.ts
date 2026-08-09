import type { RuntimeJournalEvent } from './traceState';
import type { TraceCall } from './traceProjection';
import { llmOutcome, llmResponseStatus, toolResult, type LlmOutcome } from './callInspection';

export type CallPresentationStatus = 'running' | 'waiting_retry' | 'ok' | 'error';

export type CallErrorDetails = {
  name: string;
  code?: string;
  message?: string;
  statusCode?: number;
  providerCode?: string;
  retryable?: boolean;
  retryAfterMs?: number;
};

export type CallPresentation = {
  status: CallPresentationStatus;
  durationMs?: number;
  retryCount: number;
  outcome?: LlmOutcome;
  error?: CallErrorDetails;
  tokensIn?: number;
  tokensOut?: number;
  tokensTotal?: number;
  rawEvents: RuntimeJournalEvent[];
  linkedToolCalls: RuntimeJournalEvent[];
};

const numberField = (value: unknown): number | undefined => (
  typeof value === 'number' && Number.isFinite(value) ? value : undefined
);

const textField = (value: unknown): string | undefined => (
  typeof value === 'string' && value.trim() ? value : undefined
);

function durationFor(call: TraceCall): number | undefined {
  const response = call.response;
  const payloadDuration = numberField(response?.payload.duration_ms);
  if (payloadDuration !== undefined) return payloadDuration;
  if (response?.duration_ms !== null && response?.duration_ms !== undefined) return response.duration_ms;
  if (!response) return undefined;
  const startedAt = new Date(call.request.occurred_at).getTime();
  const finishedAt = new Date(response.occurred_at).getTime();
  const elapsed = finishedAt - startedAt;
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : undefined;
}

function errorForLlm(payload: Record<string, unknown>, emptyResponse: boolean): CallErrorDetails {
  return {
    name: textField(payload.error_type) ?? (emptyResponse ? 'Пустой ответ модели' : 'Ошибка выполнения LLM'),
    code: textField(payload.error_code),
    message: textField(payload.safe_message) ?? textField(payload.user_message)
      ?? (numberField(payload.status_code) === 413
        ? 'Запрос превышает ограничение провайдера. Уменьшите контекст или лимит ответа.'
        : undefined),
    statusCode: numberField(payload.status_code),
    providerCode: textField(payload.provider_code),
    retryable: typeof payload.retryable === 'boolean' ? payload.retryable : undefined,
    retryAfterMs: numberField(payload.retry_after_ms),
  };
}

function errorForTool(payload: Record<string, unknown>): CallErrorDetails {
  const result = toolResult(payload);
  return {
    name: textField(payload.error_type) ?? textField(payload.error_code) ?? 'Ошибка выполнения инструмента',
    code: textField(payload.error_code),
    message: result.message,
    statusCode: numberField(payload.status_code),
    providerCode: textField(payload.provider_code),
    retryable: typeof payload.retryable === 'boolean' ? payload.retryable : undefined,
    retryAfterMs: numberField(payload.retry_after_ms),
  };
}

function isWaitingForRetry(call: TraceCall): boolean {
  const lastResponse = call.response;
  const lastRetry = call.retryEvents[call.retryEvents.length - 1];
  return Boolean(
    lastResponse
    && lastRetry
    && lastRetry.sequence > lastResponse.sequence
    && lastResponse.payload.retryable === true,
  );
}

/**
 * The single operator-facing interpretation of a call. Views must not read
 * raw payload status, timing or usage fields directly.
 */
export function callPresentation(call: TraceCall): CallPresentation {
  const response = call.response?.payload;
  const rawEvents = [...call.events, ...call.retryEvents, ...(call.extraction?.events ?? [])]
    .filter((event, index, events) => events.findIndex((candidate) => candidate.id === event.id) === index)
    .sort((left, right) => left.sequence - right.sequence);
  const base = {
    durationMs: durationFor(call),
    retryCount: call.retryEvents.length,
    rawEvents,
    linkedToolCalls: call.linkedToolCalls,
  };

  if (call.kind === 'error') return { ...base, status: 'error' };
  if (!response) return { ...base, status: call.retryEvents.length ? 'waiting_retry' : 'running' };

  if (call.kind === 'llm') {
    const responseStatus = llmResponseStatus(response);
    const outcome = llmOutcome(response, call.toolCallCount);
    const emptyResponse = responseStatus === 'empty';
    // Native tool calling legitimately has an empty text body.  The canonical
    // tool_call rows linked by llm_call_id are the response in that case.
    const hasToolOutcome = outcome.kind === 'tools' || call.linkedToolCalls.length > 0;
    const waitingRetry = isWaitingForRetry(call);
    const failed = !waitingRetry && (response.status === 'failed'
      || responseStatus === 'error'
      || (emptyResponse && !hasToolOutcome));
    const tokensIn = numberField(response.tokens_in);
    const tokensOut = numberField(response.tokens_out);
    return {
      ...base,
      status: waitingRetry ? 'waiting_retry' : failed ? 'error' : 'ok',
      outcome,
      error: failed ? errorForLlm(response, emptyResponse) : undefined,
      tokensIn,
      tokensOut,
      tokensTotal: numberField(response.tokens_total) ?? (tokensIn !== undefined && tokensOut !== undefined ? tokensIn + tokensOut : undefined),
    };
  }

  if (call.kind === 'tool') {
    if (call.retryEvents.length && call.retryEvents[call.retryEvents.length - 1].sequence > Number(response.sequence)) {
      return { ...base, status: 'waiting_retry' };
    }
    const failed = toolResult(response).success === false;
    return {
      ...base,
      status: failed ? 'error' : 'ok',
      error: failed ? errorForTool(response) : undefined,
    };
  }

  return { ...base, status: 'ok' };
}

export function callStatusPresentation(status: CallPresentationStatus): { label: string; tone: 'success' | 'warn' | 'danger' } {
  if (status === 'waiting_retry') return { label: 'Ожидает повтора', tone: 'warn' };
  if (status === 'error') return { label: 'Ошибка', tone: 'danger' };
  if (status === 'running') return { label: 'Выполняется', tone: 'warn' };
  return { label: 'OK', tone: 'success' };
}

export function formatCallDuration(durationMs: number | undefined): string {
  if (durationMs === undefined) return '—';
  return durationMs >= 1000 ? `${(durationMs / 1000).toFixed(1)} с` : `${durationMs} мс`;
}
