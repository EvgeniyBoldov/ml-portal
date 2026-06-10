import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Modal from '@shared/ui/Modal';
import Badge from '@shared/ui/Badge';
import Button from '@shared/ui/Button';
import { Icon } from '@shared/ui/Icon';
import { openSSE, type SSEMessage } from '@shared/lib/sse';
import { collectionsApi, type CollectionTemplate } from '@shared/api/collections';
import styles from './TemplateStatusModal.module.css';

type StageState = 'pending' | 'processing' | 'completed' | 'failed';

interface TemplateGraphStage {
  key: string;
  label: string;
  state: StageState;
  error?: string | null;
  metrics?: Record<string, unknown> | null;
}

interface TemplateStatusGraph {
  row_id: string;
  collection_id: string;
  title?: string | null;
  status?: string | null;
  description?: string | null;
  template_version?: string | null;
  template_schema?: Record<string, unknown> | null;
  analysis_nodes?: {
    description?: { status?: string | null; error?: string | null; metrics?: Record<string, unknown> | null };
    schema?: { status?: string | null; error?: string | null; metrics?: Record<string, unknown> | null };
  };
  stages?: TemplateGraphStage[];
}

interface TemplateStatusModalProps {
  collectionId: string;
  row: CollectionTemplate;
  onClose: () => void;
}

function stateTone(state: StageState): 'success' | 'warn' | 'danger' | 'neutral' {
  switch (state) {
    case 'completed':
      return 'success';
    case 'processing':
      return 'warn';
    case 'failed':
      return 'danger';
    default:
      return 'neutral';
  }
}

function stateIcon(state: StageState): string {
  switch (state) {
    case 'completed':
      return 'check';
    case 'processing':
      return 'loader';
    case 'failed':
      return 'x';
    default:
      return 'clock';
  }
}

function formatSchemaSummary(templateSchema: Record<string, unknown> | null | undefined): string {
  if (!templateSchema || typeof templateSchema !== 'object') return '—';
  const rawFields = (templateSchema as { fields?: unknown }).fields;
  const rawPlaceholders = (templateSchema as { placeholders?: unknown }).placeholders;
  const fields: unknown[] = Array.isArray(rawFields) ? rawFields : [];
  const placeholders: unknown[] = Array.isArray(rawPlaceholders) ? rawPlaceholders : [];
  if (fields.length > 0) return `${fields.length} fields`;
  if (placeholders.length > 0) return `${placeholders.length} placeholders`;
  return 'JSON';
}

function buildFallbackGraph(row: CollectionTemplate): TemplateStatusGraph {
  const status = String(row.status ?? 'uploaded').toLowerCase();
  const analysisState: StageState = status === 'ready' || status === 'analyzed' || status === 'archived'
    ? 'completed'
    : 'pending';

  return {
    row_id: row.id,
    collection_id: '',
    title: row.title,
    status,
    description: row.description,
    template_version: row.template_version,
    template_schema: row.template_schema,
    stages: [
      { key: 'uploaded', label: 'Загружен', state: 'completed' },
      {
        key: 'analysis',
        label: 'Анализ',
        state: analysisState,
        metrics: {
          description_ready: Boolean(row.description),
          schema_ready: Boolean(row.template_schema),
        },
      },
      { key: 'ready', label: 'Готово', state: status === 'ready' || status === 'archived' ? 'completed' : 'pending' },
    ],
  };
}

export function TemplateStatusModal({ collectionId, row, onClose }: TemplateStatusModalProps) {
  const queryClient = useQueryClient();
  const statusQueryKey = useMemo(
    () => ['collections', 'template-status', collectionId, row.id],
    [collectionId, row.id],
  );
  const [graph, setGraph] = useState<TemplateStatusGraph>(() => buildFallbackGraph(row));
  const [selectedStage, setSelectedStage] = useState<string>('analysis');

  const { data: statusGraph } = useQuery<TemplateStatusGraph>({
    queryKey: statusQueryKey,
    queryFn: async () => {
      const data = await collectionsApi.getTemplateStatusGraph(collectionId, row.id);
      return data as unknown as TemplateStatusGraph;
    },
    initialData: buildFallbackGraph(row),
    staleTime: Infinity,
  });

  useEffect(() => {
    setGraph(buildFallbackGraph(row));
    setSelectedStage('analysis');
  }, [row]);

  useEffect(() => {
    let disposed = false;
    const client = openSSE(
      collectionsApi.getTemplateStatusEventsUrl(collectionId, row.id),
      (events: SSEMessage[]) => {
        for (const event of events) {
          if (event.type !== 'rag.snapshot') continue;
          const data = event.data as Record<string, unknown>;
          const next = (data.graph ?? data) as TemplateStatusGraph;
          if (!disposed && next) {
            queryClient.setQueryData(statusQueryKey, next);
          }
        }
      },
    );

    return () => {
      disposed = true;
      client.disconnect();
    };
  }, [collectionId, queryClient, row.id, statusQueryKey]);

  useEffect(() => {
    if (statusGraph) {
      setGraph(statusGraph as TemplateStatusGraph);
    }
  }, [statusGraph]);

  const stages = graph.stages ?? [];
  const selected = useMemo(
    () => stages.find((stage) => stage.key === selectedStage) ?? stages[1] ?? stages[0] ?? null,
    [selectedStage, stages],
  );

  const title = graph.title || row.title || 'Статус шаблона';
  const analysisError =
    graph.analysis_nodes?.description?.error ||
    graph.analysis_nodes?.schema?.error ||
    selected?.error ||
    null;

  return (
    <Modal open onClose={onClose} title={title} size="xl" className={styles.modal}>
      <div className={styles.container}>
        <div className={styles.flow}>
          {stages.map((stage, index) => (
            <React.Fragment key={stage.key}>
              <button
                className={`${styles.stageNode} ${selectedStage === stage.key ? styles.selected : ''} ${stage.state === 'processing' ? styles.active : ''}`}
                onClick={() => setSelectedStage(stage.key)}
              >
                <div className={styles.stageIcon} data-tone={stateTone(stage.state)}>
                  <Icon name={stateIcon(stage.state)} size={18} />
                </div>
                <div className={styles.stageLabel}>{stage.label}</div>
                <Badge tone={stateTone(stage.state)}>{stage.state}</Badge>
              </button>
              {index < stages.length - 1 && <div className={styles.connector} />}
            </React.Fragment>
          ))}
        </div>

        <div className={styles.details}>
          <div className={styles.detailsHeader}>
            <div>
              <div className={styles.detailsTitle}>{selected?.label || 'Этап'}</div>
              <div className={styles.detailsSubtitle}>{graph.template_version || 'Версия не указана'}</div>
            </div>
            <Badge tone={stateTone(selected?.state ?? 'pending')}>{selected?.state ?? 'pending'}</Badge>
          </div>

          {analysisError && (
            <div className={styles.errorBox}>
              <Icon name="alert-triangle" size={16} />
              <span>{analysisError}</span>
            </div>
          )}

          <div className={styles.grid}>
            <div className={styles.row}>
              <span>Описание</span>
              <span>{graph.description || '—'}</span>
            </div>
            <div className={styles.row}>
              <span>Схема</span>
              <span>{formatSchemaSummary(graph.template_schema)}</span>
            </div>
            <div className={styles.row}>
              <span>Статус</span>
              <span>{graph.status || 'uploaded'}</span>
            </div>
          </div>

          <div className={styles.actions}>
            <Button variant="ghost" onClick={onClose}>Закрыть</Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

export default TemplateStatusModal;
