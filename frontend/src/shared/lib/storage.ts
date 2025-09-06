export type Tokens = { access_token: string; refresh_token?: string; expires_at?: number }
const KEY = 'auth.tokens.v1'

export function saveTokens(t: Tokens | null) {
  if (!t) { localStorage.removeItem(KEY); return }
  localStorage.setItem(KEY, JSON.stringify(t))
}
export function loadTokens(): Tokens | null {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null') } catch { return null }
}
