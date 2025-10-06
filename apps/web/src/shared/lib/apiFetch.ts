import { API_BASE } from '@shared/api';
import { get, set, del } from './storage';
import { idempotencyKey } from './idempotency';

type Opts = RequestInit & { auth?: boolean; idempotent?: boolean };

function token() {
  // First check localStorage
  const localToken = get<string>('token') || get<string>('access_token');
  if (localToken) return localToken;
  
  // If no token in localStorage, try to get from cookies
  // Note: We can't read HTTP-only cookies from JavaScript, so we rely on the backend
  // to check cookies if no Authorization header is provided
  return null;
}
function refreshToken() {
  return get<string>('refresh_token');
}

async function refresh() {
  const res = await fetch(API_BASE + '/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken() }),
    credentials: 'include', // Include cookies in refresh request
  });
  if (!res.ok) throw new Error('refresh failed');
  const data = await res.json();
  set('token', data.access_token);
  if (data.refresh_token) set('refresh_token', data.refresh_token);
  return data.access_token;
}

export async function apiFetch<T = any>(
  path: string,
  opts: Opts = {}
): Promise<T> {
  const url = path.startsWith('http') ? path : API_BASE + path;
  const headers: Record<string, string> = { ...((opts.headers || {}) as any) };
  
  // Set Content-Type for JSON requests
  if (opts.body && typeof opts.body === 'string' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  
  // Only add Authorization header if auth is not disabled and we have a token
  if (opts.auth !== false) {
    const authToken = token();
    if (authToken) {
      headers['Authorization'] = 'Bearer ' + authToken;
    }
    // If no token in localStorage, we still send the request with cookies
    // The backend will check cookies if no Authorization header is provided
  }
    
  if (opts.idempotent) headers['Idempotency-Key'] = idempotencyKey();
  
  const doFetch = () => fetch(url, { 
    ...opts, 
    headers,
    credentials: 'include' // Include cookies in requests
  });
  
  let res = await doFetch();
  if (res.status === 401) {
    try {
      const t = await refresh();
      headers['Authorization'] = 'Bearer ' + t;
      res = await doFetch();
    } catch {
      del('token');
      del('refresh_token');
      throw new Error('Не авторизован');
    }
  }
  if (!res.ok) {
    let msg = 'Request failed';
    try {
      const j = await res.json();
      msg = j.message || j.detail || JSON.stringify(j);
    } catch {
      // Ignore JSON parsing errors
    }
    throw new Error(msg);
  }
  return res.json();
}
