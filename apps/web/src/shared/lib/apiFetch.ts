import { API_BASE } from '@shared/api';
import { get, set, del } from './storage';
import { idempotencyKey } from './idempotency';

type Opts = RequestInit & { auth?: boolean; idempotent?: boolean };

function token() {
  return get<string>('token');
}
function refreshToken() {
  return get<string>('refresh_token');
}

async function refresh() {
  const res = await fetch(API_BASE + '/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken() }),
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
  if (opts.auth !== false && token())
    headers['Authorization'] = 'Bearer ' + token();
  if (opts.idempotent) headers['Idempotency-Key'] = idempotencyKey();
  const doFetch = () => fetch(url, { ...opts, headers });
  let res = await doFetch();
  if (res.status === 401 && token()) {
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
