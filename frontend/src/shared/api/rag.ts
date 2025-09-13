import { apiRequest } from './http'

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
  return apiRequest<{ 
    items: any[]; 
    pagination: {
      page: number;
      size: number;
      total: number;
      total_pages: number;
      has_next: boolean;
      has_prev: boolean;
    }
  }>(`/rag/?${qs.toString()}`)
}

export async function uploadFile(file: File, name?: string, tags?: string[]) {
  const fd = new FormData()
  fd.set('file', file)
  if (name) fd.set('name', name)
  if (tags?.length) fd.set('tags', JSON.stringify(tags))
  return apiRequest<{ id: string; status: string }>('/rag/upload', { method: 'POST', body: fd })
}

export async function updateRagDocumentTags(docId: string, tags: string[]) {
  return apiRequest<{ id: string; tags: string[] }>(`/rag/${docId}/tags`, { 
    method: 'PUT', 
    body: JSON.stringify(tags) 
  })
}

export async function getRagProgress(doc_id: string) {
  return apiRequest<any>(`/rag/${doc_id}/progress`)
}

export async function getRagStats() {
  return apiRequest<any>('/rag/stats')
}

export async function getRagMetrics() {
  return apiRequest<any>('/rag/metrics')
}

export async function downloadRagFile(doc_id: string, kind: 'original' | 'canonical' = 'original') {
  return apiRequest<{ url: string }>(`/rag/${doc_id}/download?kind=${kind}`)
}

export async function archiveRagDocument(doc_id: string) {
  return apiRequest<{ id: string; archived: boolean }>(`/rag/${doc_id}/archive`, { method: 'POST' })
}

export async function deleteRagDocument(doc_id: string) {
  return apiRequest<{ id: string; deleted: boolean }>(`/rag/${doc_id}`, { method: 'DELETE' })
}

export async function ragSearch(payload: { text?: string; top_k?: number; min_score?: number }) {
  return apiRequest<{ items: Array<{ document_id: string; chunk_id: string; score: number; snippet: string }> }>('/rag/search', { 
    method: 'POST', 
    body: JSON.stringify(payload) 
  })
}

export async function reindexRagDocument(doc_id: string) {
  return apiRequest<{ id: string; status: string }>(`/rag/${doc_id}/reindex`, { method: 'POST' })
}

export async function reindexAllRagDocuments() {
  return apiRequest<{ reindexed_count: number; total_documents: number }>('/rag/reindex', { method: 'POST' })
}
