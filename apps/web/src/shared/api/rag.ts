import { apiRequest } from '@shared/api/http';
import { RagDocumentsResponse, StatusGraph } from '@shared/api/types/rag';
import { DocStatus, StageKey, StageStatus, IndexModelStatus, StageState } from '@/domains/rag/types';

export async function getRagDocuments(
  page: number = 1,
  size: number = 100,
  status?: string,
  search?: string
): Promise<RagDocumentsResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    size: size.toString(),
  });

  if (status) params.append('status', status);
  if (search) params.append('search', search);

  const response = await apiRequest<RagDocumentsResponse>(`/rag?${params}`);

  // Валидация ответа
  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  const { items, pagination } = response;

  if (!Array.isArray(items)) {
    throw new Error('Поле items должно быть массивом');
  }

  if (!pagination || typeof pagination !== 'object') {
    throw new Error('Поле pagination отсутствует или имеет неверный формат');
  }

  return response;
}

/**
 * Adapter: transform StatusGraph (API) -> DocStatus (UI)
 * Exported for use in React Query select
 */
export function adaptStatusGraphToDocStatus(graph: StatusGraph): DocStatus {
  // Map backend status -> frontend StageState
  const mapState = (s: string | undefined): StageState => {
    switch (s) {
      case 'completed':
        return 'ok';
      case 'failed':
        return 'error';
      case 'processing':
        return 'running';
      case 'cancelled':
        return 'skipped';
      case 'queued':
      case 'pending':
        return s as StageState;
      default:
        return 'idle';
    }
  };
  // Map pipeline nodes to stages
  const stages: Record<StageKey, StageStatus> = {} as Record<StageKey, StageStatus>;
  
  for (const node of graph.pipeline) {
    const stageKey = node.key as StageKey;
    stages[stageKey] = {
      stage: stageKey,
      state: mapState(node.status),
      started_at: node.started_at,
      finished_at: node.finished_at,
      error: node.error,
      metrics: node.metrics,
    };
  }

  // Map embeddings to embed models (EMBEDDING column)
  const embed_models: IndexModelStatus[] = graph.embeddings.map((emb) => ({
    id: emb.model,
    name: emb.model,
    state: mapState(emb.status),
    started_at: emb.started_at,
    finished_at: emb.finished_at,
    error: emb.error,
  }));

  // Map index array to index models (INDEX column)
  const index_models: IndexModelStatus[] = (graph as any).index
    ? graph.index.map((idx) => ({
        id: idx.model,
        name: idx.model,
        state: mapState(idx.status),
        started_at: idx.started_at,
        finished_at: idx.finished_at,
        error: idx.error,
      }))
    : [];

  return {
    id: graph.doc_id,
    name: graph.doc_id, // fallback, can be enriched
    stages,
    embed_models,
    index_models,
  };
}

/**
 * Fetch raw StatusGraph from API (stored in cache as-is)
 */
export async function getRagDocumentRaw(docId: string): Promise<StatusGraph> {
  const response = await apiRequest<StatusGraph>(`/rag/${docId}/status-graph`);
  
  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }
  
  return response;
}

/**
 * Legacy: fetch and adapt immediately
 * @deprecated Use getRagDocumentRaw + adaptStatusGraphToDocStatus in select instead
 */
export async function getRagDocument(docId: string): Promise<DocStatus> {
  const graph = await getRagDocumentRaw(docId);
  return adaptStatusGraphToDocStatus(graph);
}

export async function uploadRagDocument(
  file: File,
  filename: string,
  tags: string[] = []
): Promise<{ id: string; status: string; message: string }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', filename);
  if (tags.length > 0) {
    formData.append('tags', JSON.stringify(tags));
  }

  const response = await apiRequest<{
    id: string;
    status: string;
    message: string;
  }>('/rag/upload', {
    method: 'POST',
    body: formData,
    timeout: 30000, // 30 seconds timeout
  });

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function getStatusGraph(docId: string): Promise<StatusGraph> {
  const response = await apiRequest<StatusGraph>(`/rag/${docId}/status-graph`);

  // Валидация ответа
  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  const { doc_id, pipeline, embeddings, agg_status, agg_details } = response;

  if (!doc_id || typeof doc_id !== 'string') {
    throw new Error('Поле doc_id отсутствует или имеет неверный формат');
  }

  if (!Array.isArray(pipeline)) {
    throw new Error('Поле pipeline должно быть массивом');
  }

  if (!Array.isArray(embeddings)) {
    throw new Error('Поле embeddings должно быть массивом');
  }

  if (!agg_status || typeof agg_status !== 'string') {
    throw new Error('Поле agg_status отсутствует или имеет неверный формат');
  }

  if (!agg_details || typeof agg_details !== 'object') {
    throw new Error('Поле agg_details отсутствует или имеет неверный формат');
  }

  return response;
}

export async function deleteRagDocument(
  docId: string
): Promise<{ id: string; deleted: boolean }> {
  const response = await apiRequest<{ id: string; deleted: boolean }>(
    `/rag/${docId}`,
    {
      method: 'DELETE',
    }
  );

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function startRagIngest(
  docId: string
): Promise<{ status: string; message: string; document_id: string; embedding_models: string[] }> {
  const response = await apiRequest<{
    status: string;
    message: string;
    document_id: string;
    embedding_models: string[];
  }>(`/rag/status/${docId}/ingest/start`, {
    method: 'POST',
    idempotent: true,
  });

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function resetRagDocument(
  docId: string,
  step: string = 'extract'
): Promise<{
  status: string;
  message: string;
  document_id: string;
  stage: string;
}> {
  const response = await apiRequest<{
    status: string;
    message: string;
    document_id: string;
    stage: string;
  }>(`/rag/status/${docId}/ingest/retry?stage=${step}`, {
    method: 'POST',
    idempotent: true,
  });

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function cancelRagDocument(docId: string): Promise<{
  document_id: string;
  action: string;
  canceled_jobs: number;
  message: string;
}> {
  const response = await apiRequest<{
    document_id: string;
    action: string;
    canceled_jobs: number;
    message: string;
  }>(`/rag/${docId}/cancel`, {
    method: 'POST',
  });

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function updateRagDocumentTags(
  docId: string,
  tags: string[]
): Promise<{ id: string; tags: string[] }> {
  const response = await apiRequest<{ id: string; tags: string[] }>(
    `/rag/${docId}/tags`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(tags),
    }
  );

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function updateRagDocumentScope(
  docId: string,
  scope: 'local' | 'global'
): Promise<{ id: string; scope: string; message: string }> {
  const formData = new FormData();
  formData.append('scope', scope);

  const response = await apiRequest<{
    id: string;
    scope: string;
    message: string;
  }>(`/rag/${docId}/scope`, {
    method: 'PUT',
    body: formData,
  });

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function retryNodeAction(
  docId: string,
  nodeType: 'pipeline' | 'embedding',
  nodeKey: string,
  action: 'retry' | 'skip'
): Promise<{ message: string }> {
  const response = await apiRequest<{ message: string }>(
    `/rag/${docId}/nodes/${nodeType}/${nodeKey}/actions`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ action }),
    }
  );

  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }

  return response;
}

export async function retryIngestStep(
  docId: string,
  step: 'extract' | 'chunk' | 'embed',
  modelAlias?: string
): Promise<{
  document_id: string;
  step: string;
  task_id: string;
  status: string;
}> {
  let url = `/rag/ingest/retry/${docId}/${step}`;
  if (modelAlias && step === 'embed') {
    url += `?model_alias=${encodeURIComponent(modelAlias)}`;
  }
  const response = await apiRequest<{
    document_id: string;
    step: string;
    task_id: string;
    status: string;
  }>(url, { method: 'POST' });
  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }
  return response;
}

export async function restartIngestStep(
  docId: string,
  step: 'extract' | 'normalize' | 'split' | 'embed' | 'commit',
  reason?: string
): Promise<{
  document_id: string;
  action: string;
  step: string;
  message: string;
}> {
  const response = await apiRequest<{
    document_id: string;
    action: string;
    step: string;
    message: string;
  }>(`/rag/ingest/restart/${docId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      step,
      reason: reason || `Restart from step ${step}`,
    }),
  });
  if (!response || typeof response !== 'object') {
    throw new Error('Неверный формат ответа от сервера');
  }
  return response;
}
