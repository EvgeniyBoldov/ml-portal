import { apiFetch } from './base'

export async function listDocs(params: { 
  page?: number; 
  size?: number; 
  status?: string; 
  search?: string; 
} = {}) {
  const qs = new URLSearchParams()
  if (params.page) qs.set('page', String(params.page))
  if (params.size) qs.set('size', String(params.size))
  if (params.status) qs.set('status', params.status)
  if (params.search) qs.set('search', params.search)
  const res = await apiFetch(`/rag/?${qs.toString()}`, { method: 'GET' })
  return res.json() as Promise<{ 
    items: any[]; 
    pagination: {
      page: number;
      size: number;
      total: number;
      total_pages: number;
      has_next: boolean;
      has_prev: boolean;
    }
  }>
}

export async function uploadFile(file: File, name?: string, tags?: string[]) {
  const fd = new FormData()
  fd.set('file', file)
  if (name) fd.set('name', name)
  if (tags?.length) fd.set('tags', JSON.stringify(tags))
  const res = await apiFetch('/rag/upload', { method: 'POST', body: fd })
  return res.json()
}

export async function updateRagDocumentTags(docId: string, tags: string[]) {
  const res = await apiFetch(`/rag/${docId}/tags`, { 
    method: 'PUT', 
    body: JSON.stringify(tags) 
  })
  return res.json()
}

export async function getRagProgress(doc_id: string) {
  const res = await apiFetch(`/rag/${doc_id}/progress`, { method: 'GET' })
  return res.json()
}

export async function getRagStats() {
  const res = await apiFetch('/rag/stats', { method: 'GET' })
  return res.json()
}

export async function getRagMetrics() {
  const res = await apiFetch('/rag/metrics', { method: 'GET' })
  return res.json()
}

export async function downloadRagFile(doc_id: string, kind: 'original' | 'canonical' = 'original') {
  const res = await apiFetch(`/rag/${doc_id}/download?kind=${kind}`, { method: 'GET' })
  return res.json()
}

export async function archiveRagDocument(doc_id: string) {
  const res = await apiFetch(`/rag/${doc_id}/archive`, { method: 'POST' })
  return res.json()
}

export async function deleteRagDocument(doc_id: string) {
  const res = await apiFetch(`/rag/${doc_id}`, { method: 'DELETE' })
  return res.json()
}

export async function ragSearch(payload: { text?: string; top_k?: number; min_score?: number }) {
  const res = await apiFetch('/rag/search', { method: 'POST', body: JSON.stringify(payload) })
  return res.json() as Promise<{ items: Array<{ document_id: string; chunk_id: string; score: number; snippet: string }> }>
}
