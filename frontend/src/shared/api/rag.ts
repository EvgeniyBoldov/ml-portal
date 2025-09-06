import { apiFetch } from './base'

export async function listDocs(params: { status?: string; tags?: string; q?: string; cursor?: string } = {}) {
  const qs = new URLSearchParams()
  if (params.status) qs.set('status', params.status)
  if (params.tags) qs.set('tags', params.tags)
  if (params.q) qs.set('q', params.q)
  if (params.cursor) qs.set('cursor', params.cursor)
  const res = await apiFetch(`/rag?${qs.toString()}`, { method: 'GET' })
  return res.json() as Promise<{ items: any[]; next_cursor?: string | null }>
}

export async function uploadFile(file: File, name?: string, tags?: string[]) {
  const fd = new FormData()
  fd.set('file', file)
  if (name) fd.set('name', name)
  if (tags?.length) tags.forEach(t => fd.append('tags', t))
  const res = await apiFetch('/rag/upload', { method: 'POST', body: fd })
  return res.json()
}

export async function ragSearch(payload: { text?: string; top_k?: number; min_score?: number }) {
  const res = await apiFetch('/rag/search', { method: 'POST', body: JSON.stringify(payload) })
  return res.json() as Promise<{ items: Array<{ document_id: string; chunk_id: string; score: number; snippet: string }> }>
}
