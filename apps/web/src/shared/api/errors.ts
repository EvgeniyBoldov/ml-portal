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
    if (data && typeof data === 'object') {
      // FastAPI format: {detail: "message"} or {detail: [{...}]}
      if ('detail' in data) {
        const detail = (data as any).detail;
        if (typeof detail === 'string') {
          msg = detail;
        } else if (Array.isArray(detail) && detail.length > 0) {
          // Validation errors
          msg = detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join('; ');
        }
        code = `http_${resp.status}`;
      }
      // Custom format: {error: {...}}
      else if ('error' in data) {
        const err = (data as any).error;
        msg = err?.message || msg;
        code = err?.code || code;
        requestId = (data as any).request_id;
        details = err?.details;
      }
    }
  } catch {
    // Ignore errors when parsing error response
  }
  return new ApiError(msg, code, requestId, details);
}
