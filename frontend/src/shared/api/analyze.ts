import { apiFetch } from './base'

export async function listAnalyze() {
  const res = await apiFetch('/analyze', { method: 'GET' })
  return res.json()
}

export async function uploadAnalysisFile(file: File) {
  const fd = new FormData()
  fd.set('file', file)
  const res = await apiFetch('/analyze/upload', { method: 'POST', body: fd })
  return res.json()
}

export async function getAnalyze(id: string) {
  const res = await apiFetch(`/analyze/document/${id}`, { method: 'GET' })
  return res.json()
}

export async function downloadAnalysisFile(doc_id: string, kind: 'original' | 'canonical' = 'original') {
  const res = await apiFetch(`/analyze/document/${doc_id}/download?kind=${kind}`, { method: 'GET' })
  return res.json()
}
