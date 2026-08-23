import { describe, expect, it } from 'vitest';
import { callPresentation, formatCallDuration } from './callPresentation';
import type { TraceCall } from './traceProjection';
import type { RuntimeJournalEvent, TraceEntity } from './traceState';

const entity = (id: string): TraceEntity => ({
  key: `llm_call:${id}`,
  type: 'llm_call',
  id,
  parentKey: 'agent_execution:agent-1',
  childKeys: [],
  eventIds: [],
  status: 'running',
  snapshotsByKind: {},
});

const event = (sequence: number, eventType: string, payload: Record<string, unknown>): RuntimeJournalEvent => ({
  id: `event-${sequence}`,
  run_id: 'run-1',
  sequence,
  event_type: eventType,
  occurred_at: `2026-08-05T13:30:${String(sequence).padStart(2, '0')}.000Z`,
  entity_type: eventType === 'protocol_retry' ? 'run' : 'llm_call',
  entity_id: eventType === 'protocol_retry' ? 'run-1' : 'llm-1',
  parent_entity_type: eventType === 'protocol_retry' ? null : 'agent_execution',
  parent_entity_id: eventType === 'protocol_retry' ? null : 'agent-1',
  caused_by_event_id: null,
  duration_ms: null,
  payload,
});

describe('call presentation', () => {
  it('keeps canonical request, response and retry rows intact in RAW', () => {
    const request = event(1, 'llm_request', { model: 'gemma' });
    const response = event(2, 'llm_response', {
      error_type: 'LLMProviderError',
      error_code: 'llm_rate_limited',
      status_code: 429,
      provider_code: 'rate_limit',
      retryable: true,
      retry_after_ms: 6000,
      duration_ms: 217,
    });
    const retry = event(3, 'protocol_retry', { reason: 'transport_error', attempt: 1 });
    const call: TraceCall = {
      entity: entity('llm-1'), events: [request, response], request, response,
      retryEvents: [retry], linkedToolCalls: [], kind: 'llm', title: 'LLM', toolCallCount: 0,
      info: { status: 'running', retryCount: 0 }, requestView: { messages: [] },
    };

    expect(callPresentation(call)).toMatchObject({
      status: 'waiting_retry', durationMs: 217, retryCount: 1,
      error: {
        name: 'LLMProviderError', code: 'llm_rate_limited', statusCode: 429,
        providerCode: 'rate_limit', retryable: true, retryAfterMs: 6000,
      },
    });
    expect(callPresentation(call).rawEvents).toEqual([request, response, retry]);
  });

  it('recognizes nested tool failures and derives duration from event timestamps', () => {
    const request = event(1, 'tool_call', { tool: 'file.generate' });
    const response = event(5, 'tool_result', { result: { success: false, safe_message: 'Недоступно' } });
    const call: TraceCall = {
      entity: { ...entity('tool-1'), key: 'tool_call:tool-1', type: 'tool_call' },
      events: [request, response], request, response, retryEvents: [], linkedToolCalls: [], kind: 'tool', title: 'file.generate',
      info: { status: 'running', retryCount: 0 }, requestView: { messages: [] },
    };

    expect(callPresentation(call)).toMatchObject({ status: 'error', durationMs: 4000, error: { message: 'Недоступно' } });
    expect(formatCallDuration(callPresentation(call).durationMs)).toBe('4.0 с');
  });

  it('does not mark a native tool call with an empty text body as an LLM error', () => {
    const request = event(1, 'llm_request', { model: 'gptoss' });
    const response = event(2, 'llm_response', { content: '', native_tool_calling: true });
    const tool = event(3, 'tool_call', { tool: 'collection.info', llm_call_id: 'llm-1' });
    const call: TraceCall = {
      entity: entity('llm-1'), events: [request, response], request, response,
      retryEvents: [], linkedToolCalls: [tool], kind: 'llm', title: 'LLM', toolCallCount: 1,
      info: { status: 'running', retryCount: 0 }, requestView: { messages: [] },
    };

    expect(callPresentation(call)).toMatchObject({
      status: 'ok',
      outcome: { kind: 'tools', count: 1 },
      error: undefined,
    });
  });

  it('uses a terminal failed status and exposes a useful provider-limit error', () => {
    const request = event(1, 'llm_request', { model: 'gptoss' });
    const response = event(2, 'llm_response', {
      status: 'failed',
      error_type: 'LLMProviderError',
      error_code: 'llm_request_too_large',
      status_code: 413,
      retryable: false,
    });
    const call: TraceCall = {
      entity: entity('llm-1'), events: [request, response], request, response,
      retryEvents: [], linkedToolCalls: [], kind: 'llm', title: 'LLM', toolCallCount: 0,
      info: { status: 'running', retryCount: 0 }, requestView: { messages: [] },
    };

    expect(callPresentation(call)).toMatchObject({
      status: 'error',
      error: {
        name: 'LLMProviderError',
        code: 'llm_request_too_large',
        statusCode: 413,
        message: 'Запрос превышает ограничение провайдера. Уменьшите контекст или лимит ответа.',
      },
    });
  });
});
