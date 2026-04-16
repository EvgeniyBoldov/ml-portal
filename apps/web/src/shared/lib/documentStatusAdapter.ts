/**
 * Adapter: transform StatusGraph (API response) → DocStatus (UI model).
 * Shared between collections and legacy RAG.
 */
import type {
  StatusGraph,
  DocStatus,
  StageKey,
  StageStatus,
  StageState,
  IndexModelStatus,
} from '@shared/api/types/documentStatus';

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

export function adaptStatusGraphToDocStatus(graph: StatusGraph): DocStatus {
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

  const embed_models: IndexModelStatus[] = graph.embeddings.map((emb) => ({
    id: emb.model,
    name: emb.model,
    state: mapState(emb.status),
    started_at: emb.started_at,
    finished_at: emb.finished_at,
    error: emb.error,
  }));

  const index_models: IndexModelStatus[] = Array.isArray(graph.index)
    ? graph.index.map((idx) => ({
        id: idx.model,
        name: idx.model,
        state: mapState(idx.status),
        metrics: idx.metrics,
        started_at: idx.started_at,
        finished_at: idx.finished_at,
        error: idx.error,
      }))
    : [];

  return {
    id: graph.doc_id,
    name: graph.doc_id,
    stages,
    embed_models,
    index_models,
    ingest_policy: graph.ingest_policy,
  };
}
