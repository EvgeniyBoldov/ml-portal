import { apiFetch } from './base'
import { saveTokens } from '@shared/lib/storage'

export async function login(login: string, password: string) {
  const res = await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ login, password }) })
  const data = await res.json() as any
  const expires_at = Date.now() + (data.expires_in ? data.expires_in*1000 : 50*60*1000)
  saveTokens({ access_token: data.access_token, refresh_token: data.refresh_token, expires_at })
  return data
}
export async function me() {
  const res = await apiFetch('/auth/me', { method: 'GET' })
  return res.json()
}
export async function logout() {
  await apiFetch('/auth/logout', { method: 'POST' })
  saveTokens(null)
}
