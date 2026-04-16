/**
 * Document ingest status types shared between collections and status graph UI.
 * Source of truth for StatusGraph API response shape.
 */

// ─── Pipeline / Stage types (UI-side) ──────────────────────────

export type StageKey = 'upload' | 'extract' | 'normalize' | 'chunk' | 'embedding' | 'index' | 'archive';
export type StageState = 'idle' | 'queued' | 'running' | 'ok' | 'error' | 'skipped' | 'pending';

export const STAGE_ORDER: StageKey[] = ['upload', 'extract', 'normalize', 'chunk', 'embedding', 'index', 'archive'];

export interface StageStatus {
  stage: StageKey;
  state: StageState;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  retries?: number;
  error?: string;
  metrics?: Record<string, unknown>;
}

export interface IndexModelStatus {
  id: string;
  name: string;
  state: StageState;
  version?: string;
  metrics?: Record<string, unknown>;
  started_at?: string;
  finished_at?: string;
  error?: string;
}

export interface IngestPolicyControl {
  stage: string;
  node_type: string;
  status: string;
  retry_supported: boolean;
  can_retry: boolean;
  can_stop: boolean;
}

export interface IngestPolicy {
  archived: boolean;
  start_allowed: boolean;
  start_reason?: string | null;
  active_stages: string[];
  retryable_stages: string[];
  stoppable_stages: string[];
  controls: IngestPolicyControl[];
}

export interface DocStatus {
  id: string;
  name: string;
  stages: Record<StageKey, StageStatus>;
  embed_models?: IndexModelStatus[];
  index_models?: IndexModelStatus[];
  archived?: boolean;
  ingest_policy?: IngestPolicy;
}

// ─── API response types (StatusGraph) ──────────────────────────

export interface PipelineNode {
  key: string;
  status: string;
  error?: string;
  metrics?: Record<string, unknown>;
  started_at?: string;
  finished_at?: string;
  updated_at: string;
}

export interface EmbeddingNode {
  model: string;
  version?: string;
  status: string;
  error?: string;
  metrics?: Record<string, unknown>;
  started_at?: string;
  finished_at?: string;
  updated_at: string;
}

export interface StatusGraph {
  doc_id: string;
  pipeline: PipelineNode[];
  embeddings: EmbeddingNode[];
  index: EmbeddingNode[];
  agg_status: string;
  agg_details: Record<string, unknown>;
  ingest_policy?: IngestPolicy;
}
