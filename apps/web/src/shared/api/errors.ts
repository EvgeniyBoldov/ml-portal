export type ErrorEnvelope = {
  error: { code: string; message: string; details?: unknown };
  request_id?: string;
};

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  details?: unknown;
  constructor(
    status: number,
    message: string,
    code = 'unknown_error',
    requestId?: string,
    details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
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
    const data: unknown = await resp.json();
    if (data && typeof data === 'object') {
      const record = data as Record<string, unknown>;
      // FastAPI format: {detail: "message"} or {detail: [{...}]}
      if ('detail' in record) {
        const detail = record.detail;
        if (typeof detail === 'string') {
          msg = detail;
        } else if (Array.isArray(detail) && detail.length > 0) {
          // Validation errors
          msg = detail
            .map((e) => {
              if (e && typeof e === 'object') {
                const entry = e as Record<string, unknown>;
                if (typeof entry.msg === 'string') return entry.msg;
                if (typeof entry.message === 'string') return entry.message;
              }
              return JSON.stringify(e);
            })
            .join('; ');
        }
        code = `http_${resp.status}`;
      }
      // Custom format: {error: {...}}
      else if ('error' in record && record.error && typeof record.error === 'object') {
        const err = record.error as Record<string, unknown>;
        if (typeof err.message === 'string') msg = err.message;
        if (typeof err.code === 'string') code = err.code;
        if (typeof record.request_id === 'string') requestId = record.request_id;
        details = err.details;
      }
    }
  } catch {
    // Ignore errors when parsing error response
  }
  return new ApiError(resp.status, msg, code, requestId, details);
}
