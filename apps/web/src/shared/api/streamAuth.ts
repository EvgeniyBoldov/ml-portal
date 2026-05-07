import { API_BASE } from '@/shared/config';
import { getAccessToken, refreshAccessToken } from '@/shared/api/http';

type StreamFetchOptions = {
  body: unknown;
  signal?: AbortSignal;
  idempotencyKey?: string;
};

export async function fetchStreamWithAuth(
  path: string,
  options: StreamFetchOptions,
): Promise<Response> {
  const buildHeaders = () => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    };
    const token = getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (options.idempotencyKey) {
      headers['Idempotency-Key'] = options.idempotencyKey;
    }
    return headers;
  };

  const url = `${API_BASE}${path}`;
  const makeRequest = (headers: Record<string, string>) =>
    fetch(url, {
      method: 'POST',
      headers,
      credentials: 'include',
      signal: options.signal,
      body: JSON.stringify(options.body),
    });

  let response = await makeRequest(buildHeaders());
  if (response.status !== 401) {
    return response;
  }

  await refreshAccessToken();
  response = await makeRequest(buildHeaders());
  return response;
}
