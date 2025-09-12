/* Lightweight API client with idempotency support */
import { API_BASE } from '@/shared/config/env'
const BASE = API_BASE

function withBase(path: string) {
  if (path.startsWith('http')) return path
  return `${BASE}${path}`
}

function headers(extra?: Record<string, string>) {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  // Try to get token from http.ts first, then fallback to localStorage
  const token = (window as any).__auth_tokens?.access_token || localStorage.getItem('access_token')
  if (token) {
    h['Authorization'] = `Bearer ${token}`
  }
  return { ...h, ...(extra || {}) }
}

async function request<T>(method: string, path: string, body?: any, opts: { idempotent?: boolean } = {}) {
  const init: RequestInit = {
    method,
    headers: headers(opts.idempotent ? { 'Idempotency-Key': crypto.randomUUID() } : undefined),
  }
  if (body !== undefined) init.body = JSON.stringify(body)
  const res = await fetch(withBase(path), init)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json() as Promise<T>
  // @ts-ignore
  return res.text() as unknown as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: any, opts?: { idempotent?: boolean }) => request<T>('POST', path, body, opts),
  patch: <T>(path: string, body?: any) => request<T>('PATCH', path, body),
  put:   <T>(path: string, body?: any) => request<T>('PUT', path, body),
  delete:<T>(path: string) => request<T>('DELETE', path),
}
