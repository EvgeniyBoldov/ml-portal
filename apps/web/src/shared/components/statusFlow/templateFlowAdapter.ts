import type { CollectionTemplate } from '@shared/api/collections';

import type { FlowGraphModel } from './types';
import { getDisplayStatus } from './statusFlowUtils';

export interface TemplateStatusGraphModel {
  row_id: string;
  collection_id: string;
  title?: string | null;
  status?: string | null;
  runtime_status?: string | null;
  runtime_stage?: string | null;
  approval_required?: boolean;
  approved_at?: string | null;
  approved_by?: string | null;
  has_error?: boolean;
  error_message?: string | null;
  vectorization_status?: string | null;
  indexing_status?: string | null;
  description?: string | null;
  template_version?: string | null;
  template_schema?: Record<string, unknown> | null;
  stages?: Array<{
    key: string;
    label: string;
    state: string;
    error?: string | null;
    metrics?: Record<string, unknown> | null;
    started_at?: string | null;
    finished_at?: string | null;
  }>;
}

export function buildTemplateFallbackGraph(row: CollectionTemplate): TemplateStatusGraphModel {
  const status = String(row.runtime_status ?? row.status ?? 'uploaded').toLowerCase();
  const schemaDone = Boolean(row.template_schema);
  const descriptionDone = Boolean(row.description);
  const approvalDone = status === 'ready' || status === 'archived';
  const vectorDone = approvalDone;

  return {
    row_id: row.id,
    collection_id: '',
    title: row.title,
    status,
    runtime_status: status,
    description: row.description,
    template_version: row.template_version,
    template_schema: row.template_schema,
    stages: [
      { key: 'uploaded', label: 'Загружен', state: 'completed' },
      { key: 'schema', label: 'Чтение схемы', state: schemaDone ? 'completed' : 'pending' },
      { key: 'description', label: 'Создание описания', state: descriptionDone ? 'completed' : 'pending' },
      { key: 'approval', label: 'Утверждение', state: approvalDone ? 'completed' : 'pending' },
      { key: 'vectorization', label: 'Векторизация', state: vectorDone ? 'completed' : 'pending' },
      { key: 'indexing', label: 'Индексация', state: vectorDone ? 'completed' : 'pending' },
      { key: 'ready', label: 'Готово', state: status === 'ready' || status === 'archived' ? 'completed' : 'pending' },
    ],
  };
}

export function adaptTemplateStatusGraphToFlowModel(graph: TemplateStatusGraphModel): FlowGraphModel {
  return {
    pipeline: (graph.stages ?? []).map((stage) => ({
      key: stage.key,
      label: stage.label,
      status: getDisplayStatus(stage.state),
      error: stage.error,
      metrics: stage.metrics,
      started_at: stage.started_at,
      finished_at: stage.finished_at,
    })),
  };
}
