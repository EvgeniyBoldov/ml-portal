import { apiFetch } from './base'

export async function listAnalyze() {
  const res = await apiFetch('/analyze', { method: 'GET' })
  return res.json()
}

export async function createAnalyze(payload: { url?: string; file?: File }) {
  if (payload.file) {
    const fd = new FormData()
    fd.set('file', payload.file)
    const res = await apiFetch('/analyze', { method: 'POST', body: fd })
    return res.json()
  }
  const res = await apiFetch('/analyze', { method: 'POST', body: JSON.stringify({ url: payload.url }) })
  return res.json()
}

export async function getAnalyze(id: string) {
  const res = await apiFetch(`/analyze/${id}`, { method: 'GET' })
  return res.json()
}
