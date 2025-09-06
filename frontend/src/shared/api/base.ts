import { loadTokens, saveTokens } from '@shared/lib/storage'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

type FetchOpts = RequestInit & { idempotencyKey?: string }

async function refreshToken() {
  const tokens = loadTokens()
  if (!tokens?.refresh_token) return null
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: tokens.refresh_token })
  })
  if (!res.ok) { saveTokens(null); return null }
  const data = await res.json() as any
  const expires_at = Date.now() + (data.expires_in ? data.expires_in*1000 : 50*60*1000)
  const newTokens = { access_token: data.access_token, refresh_token: data.refresh_token ?? tokens.refresh_token, expires_at }
  saveTokens(newTokens)
  return newTokens
}

export async function apiFetch(path: string, opts: FetchOpts = {}) {
  const tokens = loadTokens()
  const headers: Record<string,string> = { ...(opts.headers as Record<string,string> || {}) }
  if (!headers['Content-Type'] && !(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  if (tokens?.access_token) headers['Authorization'] = `Bearer ${tokens.access_token}`
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey

  let res = await fetch(`${API_BASE}${path}`, { ...opts, headers })

  // If unauthorized, try refresh once
  if (res.status === 401 && tokens?.refresh_token) {
    const newTokens = await refreshToken()
    if (newTokens?.access_token) {
      headers['Authorization'] = `Bearer ${newTokens.access_token}`
      res = await fetch(`${API_BASE}${path}`, { ...opts, headers })
    }
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res
}
