import { describe, expect, it } from 'vitest';
import { toApiError } from './errors';

describe('toApiError', () => {
  it('preserves RFC 7807 application code, details, and trace ID', async () => {
    const error = await toApiError(new Response(JSON.stringify({
      type: 'about:blank',
      title: 'Runtime startup failed',
      status: 503,
      detail: 'The runtime could not be started.',
      code: 'CHAT_RUNTIME_START_FAILED',
      details: { run_id: 'run-1', status: 'failed' },
      trace_id: 'trace-1',
    }), { status: 503, statusText: 'Service Unavailable' }));

    expect(error).toMatchObject({
      status: 503,
      message: 'The runtime could not be started.',
      code: 'CHAT_RUNTIME_START_FAILED',
      details: { run_id: 'run-1', status: 'failed' },
      requestId: 'trace-1',
    });
  });

  it('keeps the legacy FastAPI detail contract', async () => {
    const error = await toApiError(new Response(JSON.stringify({ detail: 'Conflict' }), {
      status: 409,
      statusText: 'Conflict',
    }));
    expect(error).toMatchObject({ status: 409, message: 'Conflict', code: 'http_409' });
  });

  it('keeps the nested error envelope contract', async () => {
    const error = await toApiError(new Response(JSON.stringify({
      error: { code: 'turn_failed', message: 'Failed', details: { attempt: 2 } },
      request_id: 'request-1',
    }), { status: 500, statusText: 'Internal Server Error' }));
    expect(error).toMatchObject({
      code: 'turn_failed',
      message: 'Failed',
      details: { attempt: 2 },
      requestId: 'request-1',
    });
  });
});
