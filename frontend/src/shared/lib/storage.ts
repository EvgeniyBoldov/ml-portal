export type Tokens = { access_token: string; refresh_token?: string; expires_at?: number }
const KEY = 'auth.tokens.v1'

// ===== Generic helpers used across the app (apiFetch, etc.) =====
export function set(key: string, value: any) {
  if (value === undefined || value === null) { localStorage.removeItem(key); return }
  if (typeof value === 'string') localStorage.setItem(key, value)
  else localStorage.setItem(key, JSON.stringify(value))
}

export function get<T = string>(key: string): T | null {
  const raw = localStorage.getItem(key)
  if (raw === null) return null
  try { return JSON.parse(raw) as T } catch { return raw as unknown as T }
}

export function del(key: string) { localStorage.removeItem(key) }

// ===== Token helpers kept for backwards compatibility =====
export function saveTokens(t: Tokens | null) {
  if (!t) {
    localStorage.removeItem(KEY)
    del('token'); del('refresh_token')
    return
  }
  localStorage.setItem(KEY, JSON.stringify(t))
  // Mirror into flat keys for legacy code paths
  set('token', t.access_token)
  if (t.refresh_token) set('refresh_token', t.refresh_token); else del('refresh_token')
}

export function loadTokens(): Tokens | null {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null') } catch { return null }
}
