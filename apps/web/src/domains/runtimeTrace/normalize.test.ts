import { describe, expect, it } from 'vitest';
import { buildRunTrace, normalizeTraceEvent } from './normalize';

describe('runtimeTrace normalize', () => {
  it('maps known event to semantic category and title', () => {
    const event = normalizeTraceEvent({
      id: '1',
      raw_type: 'operation_call',
      data: { operation_slug: 'collection.document.search', arguments: { query: 'x' }, step: 2 },
    });

    expect(event.category).toBe('operation');
    expect(event.title).toBe('Вызов операции');
    expect(event.iteration).toBe(2);
    expect(event.inputs).toEqual({ arguments: { query: 'x' } });
  });

  it('maps retry and error statuses', () => {
    const retry = normalizeTraceEvent({
      id: '2',
      raw_type: 'protocol_retry',
      data: { reason: 'no_operation_call_before_answer' },
    });
    const failedOp = normalizeTraceEvent({
      id: '3',
      raw_type: 'operation_result',
      data: { success: false, operation_slug: 'x' },
    });

    expect(retry.category).toBe('retry');
    expect(retry.status).toBe('warn');
    expect(failedOp.status).toBe('error');
  });

  it('groups events by iteration', () => {
    const trace = buildRunTrace([
      { id: 'a', raw_type: 'user_request', data: { content: 'hello', step: 0 }, step_number: 0 },
      { id: 'b', raw_type: 'llm_call', data: { step: 1, response_length: 120 }, step_number: 1 },
      { id: 'c', raw_type: 'operation_call', data: { step: 1, operation_slug: 'search' }, step_number: 2 },
    ]);

    expect(trace.total_events).toBe(3);
    expect(trace.iterations).toHaveLength(2);
    expect(trace.iterations[1].events).toHaveLength(2);
  });

  it('falls back unknown types to system', () => {
    const event = normalizeTraceEvent({
      id: 'z',
      raw_type: 'brand_new_event',
      data: { a: 1 },
    });

    expect(event.category).toBe('system');
    expect(event.title).toContain('brand_new_event');
  });
});
