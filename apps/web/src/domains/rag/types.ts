/**
 * RAG domain types
 */

export type StageKey = 'upload' | 'extract' | 'normalize' | 'chunk' | 'embedding' | 'index' | 'archive';
export type StageState = 'idle' | 'queued' | 'running' | 'ok' | 'error' | 'skipped';

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
  started_at?: string;
  finished_at?: string;
  error?: string;
}

export interface DocStatus {
  id: string;
  name: string;
  stages: Record<StageKey, StageStatus>;
  embed_models?: IndexModelStatus[];
  index_models?: IndexModelStatus[];
  archived?: boolean;
}

/**
 * Reset all stages after given stage to idle/queued
 */
export function resetDownstream(status: DocStatus, from: StageKey): DocStatus {
  const fromIndex = STAGE_ORDER.indexOf(from);
  const tail = STAGE_ORDER.slice(fromIndex + 1);
  
  const updatedStages = { ...status.stages };
  tail.forEach(stage => {
    updatedStages[stage] = {
      ...updatedStages[stage],
      state: 'idle',
      started_at: undefined,
      finished_at: undefined,
      duration_ms: undefined,
      error: undefined,
    };
  });

  // Reset models if embedding or index is in tail
  const updatedModels = (tail.includes('embedding') || tail.includes('index'))
    ? status.index_models?.map(m => ({ ...m, state: 'idle' as StageState, error: undefined }))
    : status.index_models;

  return {
    ...status,
    stages: updatedStages,
    index_models: updatedModels,
  };
}

/**
 * Aggregate index stage state from models
 */
export function aggregateIndexState(models?: IndexModelStatus[]): StageState {
  if (!models || models.length === 0) return 'idle';
  
  if (models.some(m => m.state === 'error')) return 'error';
  if (models.some(m => m.state === 'running')) return 'running';
  if (models.some(m => m.state === 'queued')) return 'queued';
  if (models.every(m => m.state === 'ok')) return 'ok';
  if (models.some(m => m.state === 'skipped')) return 'skipped';
  
  return 'idle';
}
