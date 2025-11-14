export interface RagDocument {
  id: string;
  name: string;
  agg_status:
    | 'uploaded'
    | 'processing'
    | 'normalized'
    | 'chunked'
    | 'embedding'
    | 'ready'
    | 'failed'
    | 'archived';
  agg_details_json?: Record<string, unknown>;
  scope: 'local' | 'global';
  created_at: string;
  updated_at: string;
  tags?: string[];
  size?: number;
  content_type?: string;
  vectorized_models?: string[];
  tenant_name?: string;
  // Embedding progress for derived 'partial' state
  emb_status?: EmbeddingProgress[];
}

export interface EmbeddingProgress {
  model: string;
  done: number;
  total: number;
  status: string;
  hasError?: boolean;
  lastError?: string;
}

// Status graph types (source of truth from API)
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
}

export interface RagDocumentsResponse {
  items: RagDocument[];
  pagination: {
    page: number;
    size: number;
    total: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

// SSE Event types for real-time updates
export type RagEventType =
  | 'rag.status'
  | 'rag.embed.progress'
  | 'rag.tags.updated'
  | 'rag.deleted';

export interface BaseRagEvent {
  type: RagEventType;
  doc_id: string;
  timestamp: string;
  seq: number;
}

export interface RagStatusEvent extends BaseRagEvent {
  type: 'rag.status';
  data: {
    status: string;
    details?: Record<string, unknown>;
  };
}

export interface RagEmbedProgressEvent extends BaseRagEvent {
  type: 'rag.embed.progress';
  data: {
    model: string;
    version?: string;
    progress: number;
    status: string;
    metrics?: Record<string, unknown>;
    error?: string;
  };
}

export interface RagTagsUpdatedEvent extends BaseRagEvent {
  type: 'rag.tags.updated';
  data: {
    tags: string[];
  };
}

export interface RagDeletedEvent extends BaseRagEvent {
  type: 'rag.deleted';
  data: Record<string, never>;
}

export type RagEvent =
  | RagStatusEvent
  | RagEmbedProgressEvent
  | RagTagsUpdatedEvent
  | RagDeletedEvent;
