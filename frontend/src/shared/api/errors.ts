export type ErrorEnvelope = {
  error: { code: string; message: string; details?: unknown };
  request_id?: string;
};

export class ApiError extends Error {
  code: string;
  requestId?: string;
  details?: unknown;
  constructor(
    message: string,
    code = 'unknown_error',
    requestId?: string,
    details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export async function toApiError(resp: Response): Promise<ApiError> {
  let msg = `${resp.status} ${resp.statusText}`;
  let code = 'http_error';
  let requestId: string | undefined;
  let details: unknown;
  try {
    const data = await resp.json();
    if (data && typeof data === 'object' && 'error' in data) {
      const err = (data as any).error;
      msg = err?.message || msg;
      code = err?.code || code;
      requestId = (data as any).request_id;
      details = err?.details;
    }
  } catch {
    // Ignore errors when parsing error response
  }
  return new ApiError(msg, code, requestId, details);
}
