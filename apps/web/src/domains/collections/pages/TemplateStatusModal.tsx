import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import Modal from '@shared/ui/Modal';
import { openSSE, type SSEMessage } from '@shared/lib/sse';
import { collectionsApi, type CollectionTemplate } from '@shared/api/collections';
import {
  StatusFlowDetails,
  StatusFlowView,
  adaptTemplateStatusGraphToFlowModel,
  buildTemplateFallbackGraph,
  useStatusFlowSelection,
  type FlowNode,
  type FlowDetailItem,
} from '@shared/components/statusFlow';
import type { TemplateStatusGraphModel } from '@shared/components/statusFlow/templateFlowAdapter';
import statusModalStyles from '@/domains/rag/components/StatusModalNew.module.css';

import { summarizeTemplateSchema } from '@shared/lib/templateSchemaSummary';

interface TemplateStatusModalProps {
  collectionId: string;
  row: CollectionTemplate;
  onClose: () => void;
}

export function TemplateStatusModal({ collectionId, row, onClose }: TemplateStatusModalProps) {
  const queryClient = useQueryClient();
  const statusQueryKey = useMemo(
    () => ['collections', 'template-status', collectionId, row.id],
    [collectionId, row.id],
  );
  const [graph, setGraph] = useState<TemplateStatusGraphModel>(() => buildTemplateFallbackGraph(row));

  const { data: statusGraph } = useQuery<TemplateStatusGraphModel>({
    queryKey: statusQueryKey,
    queryFn: async () => {
      const data = await collectionsApi.getTemplateStatusGraph(collectionId, row.id);
      return data as unknown as TemplateStatusGraphModel;
    },
    initialData: buildTemplateFallbackGraph(row),
    staleTime: Infinity,
  });

  useEffect(() => {
    setGraph(buildTemplateFallbackGraph(row));
  }, [row]);

  useEffect(() => {
    let disposed = false;
    const client = openSSE(
      collectionsApi.getTemplateStatusEventsUrl(collectionId, row.id),
      (events: SSEMessage[]) => {
        for (const event of events) {
          if (event.type !== 'rag.snapshot') continue;
          const data = event.data as Record<string, unknown>;
          const next = (data.graph ?? data) as TemplateStatusGraphModel;
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
      setGraph(statusGraph);
    }
  }, [statusGraph]);

  const flowModel = useMemo(() => adaptTemplateStatusGraphToFlowModel(graph), [graph]);
  const { selection, setSelection } = useStatusFlowSelection(flowModel);

  const selectedNode = useMemo(() => {
    if (!selection.nodeKey) return null;
    return flowModel.pipeline.find((item) => item.key === selection.nodeKey) ?? null;
  }, [flowModel, selection.nodeKey]);

  const selectedStage = useMemo(
    () => graph.stages?.find((stage) => stage.key === selectedNode?.key) ?? null,
    [graph.stages, selectedNode?.key],
  );

  const infoItems = useMemo<FlowDetailItem[]>(() => {
    if (!selectedNode || selectedNode.error) return [];
    const metrics = (selectedStage?.metrics ?? {}) as Record<string, unknown>;
    const items: FlowDetailItem[] = [];
    switch (selectedNode.key) {
      case 'uploaded':
        if (metrics.filename) items.push({ label: 'Файл', value: String(metrics.filename) });
        if (metrics.format) items.push({ label: 'Формат', value: String(metrics.format) });
        if (metrics.content_type) items.push({ label: 'Тип', value: String(metrics.content_type) });
        if (metrics.file_size) items.push({ label: 'Размер', value: Number(metrics.file_size) });
        if (Array.isArray(metrics.sheet_names) && metrics.sheet_names.length > 0) {
          items.push({ label: 'Листы', value: metrics.sheet_names as string[] });
        }
        break;
      case 'schema':
        if (metrics.title) items.push({ label: 'Заголовок', value: String(metrics.title) });
        if (metrics.version) items.push({ label: 'Версия', value: String(metrics.version) });
        if (metrics.format) items.push({ label: 'Формат', value: String(metrics.format) });
        if (metrics.schema_summary) items.push({ label: 'Схема', value: String(metrics.schema_summary) });
        if (Array.isArray(metrics.sheet_names) && metrics.sheet_names.length > 0) {
          items.push({ label: 'Листы', value: metrics.sheet_names as string[] });
        }
        if (Array.isArray(metrics.schema_preview) && metrics.schema_preview.length > 0) {
          items.push({ label: 'Поля', value: (metrics.schema_preview as string[]).join(', ') });
        } else {
          items.push({ label: 'Поля', value: summarizeTemplateSchema(graph.template_schema) });
        }
        break;
      case 'description':
        if (metrics.title) items.push({ label: 'Заголовок', value: String(metrics.title) });
        if (metrics.version) items.push({ label: 'Версия', value: String(metrics.version) });
        items.push({ label: 'Описание', value: String(metrics.description_text ?? graph.description ?? '—') });
        break;
      case 'approval':
        items.push({ label: 'Статус', value: String(metrics.approval_state ?? 'pending') });
        if (metrics.approved_by ?? graph.approved_by) {
          items.push({ label: 'Утвердил', value: String(metrics.approved_by ?? graph.approved_by) });
        }
        if (metrics.approved_at ?? graph.approved_at) {
          items.push({ label: 'Утверждено', value: String(metrics.approved_at ?? graph.approved_at) });
        }
        break;
      case 'vectorization':
        if (metrics.model_alias) items.push({ label: 'Модель', value: String(metrics.model_alias) });
        if (metrics.chunks_prepared !== undefined) items.push({ label: 'Подготовлено чанков', value: Number(metrics.chunks_prepared) });
        if (metrics.chunk_count !== undefined) items.push({ label: 'Чанков', value: Number(metrics.chunk_count) });
        break;
      case 'indexing':
        if (metrics.model_alias) items.push({ label: 'Модель', value: String(metrics.model_alias) });
        if (metrics.indexed_count !== undefined) items.push({ label: 'Проиндексировано', value: Number(metrics.indexed_count) });
        if (metrics.chunk_count !== undefined) items.push({ label: 'Чанков', value: Number(metrics.chunk_count) });
        break;
      case 'ready':
        if (graph.template_version) items.push({ label: 'Версия', value: graph.template_version });
        items.push({ label: 'Статус', value: String(graph.runtime_status ?? graph.status ?? 'uploaded') });
        items.push({ label: 'Схема', value: summarizeTemplateSchema(graph.template_schema) });
        if (graph.approved_by) items.push({ label: 'Утвердил', value: String(graph.approved_by) });
        break;
      default:
        break;
    }
    return items;
  }, [graph, selectedNode, selectedStage?.metrics]);

  const selectedNodeForDetails = useMemo<FlowNode | null>(() => {
    if (!selectedNode) return null;
    const metrics = { ...(selectedNode.metrics ?? {}) };
    const hiddenMetricKeysByStage: Record<string, string[]> = {
      uploaded: ['filename', 'format', 'content_type', 'file_size', 'source', 'sheet_names', 'sheet_count'],
      schema: ['title', 'version', 'format', 'schema_summary', 'schema_preview', 'sheet_names'],
      description: ['title', 'version', 'description_text'],
      approval: ['approval_state', 'approved_by', 'approved_at'],
      vectorization: ['model_alias', 'chunks_prepared', 'chunk_count'],
      indexing: ['model_alias', 'chunk_count', 'indexed_count'],
      ready: ['runtime_status', 'title', 'version', 'approved_by', 'approved_at'],
    };
    for (const key of hiddenMetricKeysByStage[selectedNode.key] ?? []) {
      delete metrics[key];
    }
    return {
      ...selectedNode,
      metrics,
    };
  }, [selectedNode]);

  const metricLabels = useMemo<Record<string, string>>(
    () => ({
      filename: 'Файл',
      content_type: 'Тип',
      file_size: 'Размер',
      format: 'Формат',
      source: 'Источник',
      sheet_count: 'Листов',
      sheet_names: 'Листы',
      token_count: 'Плейсхолдеров',
      scalar_key_count: 'Скалярных ключей',
      table_prefix_count: 'Табличных префиксов',
      table_region_count: 'Табличных регионов',
      fence_block_count: 'Блоков',
      field_count: 'Полей',
      scalar_field_count: 'Скалярных полей',
      table_field_count: 'Таблиц',
      schema_summary: 'Схема',
      schema_preview: 'Поля',
      description_text: 'Описание',
      description_source: 'Источник описания',
      approval_state: 'Статус',
      approved_by: 'Утвердил',
      approved_at: 'Утверждено',
      description_edited: 'Описание изменено',
      schema_edited: 'Схема изменена',
      model_alias: 'Модель',
      chunks_prepared: 'Подготовлено чанков',
      chunk_count: 'Чанков',
      indexed_count: 'Проиндексировано',
      error_type: 'Тип ошибки',
    }),
    [],
  );

  const title = graph.title || row.title || 'Статус шаблона';

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      size="xl"
      className={statusModalStyles.modal}
    >
      <div className={statusModalStyles.container}>
        <div className={statusModalStyles.pipelineSection}>
          <StatusFlowView
            model={flowModel}
            selection={selection}
            onSelect={setSelection}
          />
        </div>
        <div className={statusModalStyles.detailsSection}>
          <StatusFlowDetails
            node={selectedNodeForDetails}
            infoItems={infoItems}
            metricLabels={metricLabels}
            processingText="Этап выполняется..."
          />
        </div>
      </div>
    </Modal>
  );
}

export default TemplateStatusModal;
