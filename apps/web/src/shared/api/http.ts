import { API_BASE } from '@/shared/config';
import { ApiError, toApiError } from '@/shared/api/errors';
import { idempotencyKey } from '@/shared/lib/idempotency';

export interface RequestOptions extends RequestInit {
  idempotent?: boolean;
  timeout?: number;
  skipAuthRedirect?: boolean; // Skip redirect to login on 401
}

export type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
};

// Access token lives ONLY in memory (module-level variable)
// Refresh token is stored in httpOnly cookie by backend
let _accessToken: string | null = null;
let _refreshPromise: Promise<void> | null = null;

// Callback for auth failure - will redirect to login
let _onAuthFailure: (() => void) | null = null;

export function setOnAuthFailure(callback: () => void) {
  _onAuthFailure = callback;
}

const ensureAbortController = (): typeof globalThis.AbortController => {
  if (
    typeof globalThis === 'undefined' ||
    typeof globalThis.AbortController !== 'function'
  ) {
    throw new Error('AbortController is not supported in this environment');
  }
  return globalThis.AbortController;
};

export function setAuthTokens(tokens: AuthTokens | null) {
  _accessToken = tokens?.access_token || null;
  // Refresh token is managed by httpOnly cookie, not stored in memory
}

export function clearAuthTokens() {
  _accessToken = null;
  // Refresh token cookie will be cleared by /logout endpoint
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export async function apiRequest<T>(
  path: string,
  opts: RequestOptions = {}
): Promise<T> {
  const url = path.startsWith('http')
    ? path
    : API_BASE.replace(/\/$/, '') + path;
  
  console.log('[apiRequest]', { path, API_BASE, url });

  // Create AbortController for timeout
  const AbortControllerCtor = ensureAbortController();
  const controller = new AbortControllerCtor();
  const timeoutId = opts.timeout
    ? setTimeout(() => controller.abort(), opts.timeout)
    : null;

  // Combine signals
  const signal = opts.signal
    ? (() => {
        const CombinedAbortController = ensureAbortController();
        const combinedController = new CombinedAbortController();
        const abort = () => combinedController.abort();
        opts.signal?.addEventListener('abort', abort);
        controller.signal.addEventListener('abort', abort);
        return combinedController.signal;
      })()
    : controller.signal;

  const headers = new Headers(opts.headers || {});
  if (!headers.has('Content-Type') && !(opts.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  if (_accessToken && !headers.has('Authorization'))
    headers.set('Authorization', `Bearer ${_accessToken}`);
  const method = (opts.method || 'GET').toUpperCase();
  if ((method !== 'GET' && method !== 'HEAD') || opts.idempotent) {
    if (!headers.has('Idempotency-Key'))
      headers.set('Idempotency-Key', idempotencyKey());
  }

  // Serialize body to JSON if it's an object (not FormData or string)
  let body = opts.body;
  if (body && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof Blob)) {
    body = JSON.stringify(body);
  }

  try {
    const attempt = () =>
      fetch(url, { ...opts, body, headers, credentials: 'include', signal });
    let resp = await attempt();
    if (resp.status === 401 && !opts.skipAuthRedirect) {
      try {
        // Try to refresh using httpOnly cookie
        await refreshAccessToken();
        const retryHeaders = new Headers(headers);
        if (_accessToken)
          retryHeaders.set('Authorization', `Bearer ${_accessToken}`);
        resp = await fetch(url, {
          ...opts,
          body,
          headers: retryHeaders,
          credentials: 'include',
          signal,
        });
      } catch {
        // Refresh failed - redirect to login
        _accessToken = null;
        if (_onAuthFailure) {
          _onAuthFailure();
        }
        throw new ApiError(401, 'Session expired. Please login again.');
      }
    }
    if (!resp.ok) {
      const error = await toApiError(resp);
      // If still 401 after refresh attempt, redirect to login
      if (error.status === 401 && !opts.skipAuthRedirect && _onAuthFailure) {
        _accessToken = null;
        _onAuthFailure();
      }
      throw error;
    }
    if (resp.status === 204) return undefined as unknown as T;
    const ct = resp.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) {
      const data = await resp.json();
      return data as T;
    }
    return (await resp.text()) as unknown as T;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

export async function refreshAccessToken(): Promise<void> {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const url = API_BASE.replace(/\/$/, '') + '/auth/refresh';
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'include', // Send httpOnly cookie automatically
    });
    if (!resp.ok) {
      _refreshPromise = null;
      _accessToken = null;
      throw await toApiError(resp);
    }
    const data = await resp.json();
    _accessToken = data.access_token;
    // Refresh token is updated in httpOnly cookie by backend
    _refreshPromise = null;
  })();
  return _refreshPromise;
}
