import { API_BASE } from '@/shared/config/env';
import { ApiError, toApiError } from '@/shared/api/errors';
import { idempotencyKey } from '@/shared/lib/idempotency';

export type RequestOptions = RequestInit & { idempotent?: boolean };

export type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
};
let _tokens: AuthTokens | null = null;
let _refreshPromise: Promise<void> | null = null;

export function setAuthTokens(tokens: AuthTokens | null) {
  _tokens = tokens;
  // Also save to global state for client.ts
  (window as any).__auth_tokens = tokens;
  if (tokens?.access_token) {
    localStorage.setItem('access_token', tokens.access_token);
  } else {
    localStorage.removeItem('access_token');
  }
}
export function clearAuthTokens() {
  _tokens = null;
  (window as any).__auth_tokens = null;
  localStorage.removeItem('access_token');
}
export function getAccessToken(): string | null {
  return _tokens?.access_token || null;
}

export async function apiRequest<T>(
  path: string,
  opts: RequestOptions = {}
): Promise<T> {
  const url = path.startsWith('http')
    ? path
    : API_BASE.replace(/\/$/, '') + path;
  const headers = new Headers(opts.headers || {});
  if (!headers.has('Content-Type') && !(opts.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  if (_tokens?.access_token && !headers.has('Authorization'))
    headers.set('Authorization', `Bearer ${_tokens.access_token}`);
  const method = (opts.method || 'GET').toUpperCase();
  if ((method !== 'GET' && method !== 'HEAD') || opts.idempotent) {
    if (!headers.has('Idempotency-Key'))
      headers.set('Idempotency-Key', idempotencyKey());
  }
  const attempt = () => fetch(url, { ...opts, headers });
  let resp = await attempt();
  if (resp.status === 401 && _tokens?.refresh_token) {
    try {
      await refreshAccessToken();
      const retryHeaders = new Headers(headers);
      if (_tokens?.access_token)
        retryHeaders.set('Authorization', `Bearer ${_tokens.access_token}`);
      resp = await fetch(url, { ...opts, headers: retryHeaders });
    } catch {
      // Ignore refresh errors
    }
  }
  if (!resp.ok) throw await toApiError(resp);
  if (resp.status === 204) return undefined as unknown as T;
  const ct = resp.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) return (await resp.json()) as T;
  return (await resp.text()) as unknown as T;
}

export async function refreshAccessToken(): Promise<void> {
  if (_refreshPromise) return _refreshPromise;
  if (!_tokens?.refresh_token)
    throw new ApiError('No refresh token', 'no_refresh_token');
  _refreshPromise = (async () => {
    const url = API_BASE.replace(/\/$/, '') + '/auth/refresh';
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ refresh_token: _tokens!.refresh_token }),
    });
    if (!resp.ok) {
      _refreshPromise = null;
      _tokens = null;
      throw await toApiError(resp);
    }
    const data = await resp.json();
    _tokens = {
      access_token: data.access_token,
      refresh_token: data.refresh_token ?? _tokens!.refresh_token,
      expires_in: data.expires_in,
    };
    // Update global state and localStorage
    (window as any).__auth_tokens = _tokens;
    localStorage.setItem('access_token', _tokens.access_token);
    _refreshPromise = null;
  })();
  return _refreshPromise;
}
