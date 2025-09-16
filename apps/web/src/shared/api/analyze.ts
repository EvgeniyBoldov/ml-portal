import { apiRequest } from './http';

export async function listAnalyze() {
  return apiRequest<{ items: any[] }>('/analyze');
}

export async function uploadAnalysisFile(file: File) {
  const fd = new FormData();
  fd.set('file', file);
  return apiRequest<{ id: string; status: string }>('/analyze/upload', {
    method: 'POST',
    body: fd,
  });
}

export async function getAnalyze(id: string) {
  return apiRequest<any>(`/analyze/${id}`);
}

export async function downloadAnalysisFile(
  doc_id: string,
  kind: 'original' | 'canonical' = 'original'
) {
  return apiRequest<{ url: string }>(
    `/analyze/${doc_id}/download?kind=${kind}`
  );
}

export async function deleteAnalysisFile(doc_id: string) {
  return apiRequest<{ id: string; deleted: boolean }>(`/analyze/${doc_id}`, {
    method: 'DELETE',
  });
}

export async function reanalyzeFile(doc_id: string) {
  return apiRequest<{ id: string; status: string }>(
    `/analyze/${doc_id}/reanalyze`,
    { method: 'POST' }
  );
}
