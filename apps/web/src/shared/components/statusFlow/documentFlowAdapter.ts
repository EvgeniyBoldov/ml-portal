import type { DocStatus } from '@shared/api/types/documentStatus';

import type { FlowGraphModel } from './types';
import { getDisplayStatus } from './statusFlowUtils';

export function adaptDocumentStatusToFlowModel(
  docStatus: DocStatus | undefined
): FlowGraphModel {
  if (!docStatus?.stages) {
    return { pipeline: [] };
  }

  const pipelineKeys: Array<'upload' | 'extract' | 'normalize' | 'chunk'> = [
    'upload',
    'extract',
    'normalize',
    'chunk',
  ];
  const pipeline = pipelineKeys.map(key => {
    const stage = docStatus.stages[key];
    return {
      key,
      label: {
        upload: 'Загрузка файла',
        extract: 'Извлечение текста',
        normalize: 'Нормализация документа',
        chunk: 'Разбиение на фрагменты',
      }[key],
      status: getDisplayStatus(stage?.state),
      error: stage?.error,
      metrics: stage?.metrics,
      started_at: stage?.started_at ?? null,
      finished_at: stage?.finished_at ?? null,
    };
  });

  const embeddings = (docStatus.embed_models ?? []).map(item => ({
    key: item.id || item.name,
    label: `Векторизация · ${item.name || item.id}`,
    status: getDisplayStatus(item.state),
    version: item.version ?? null,
    error: item.error,
    metrics: item.metrics,
    started_at: item.started_at ?? null,
    finished_at: item.finished_at ?? null,
  }));

  const indexes = (docStatus.index_models ?? []).map(item => ({
    key: item.id || item.name,
    label: `Индексирование · ${item.name || item.id}`,
    status: getDisplayStatus(item.state),
    version: item.version ?? null,
    error: item.error,
    metrics: item.metrics,
    started_at: item.started_at ?? null,
    finished_at: item.finished_at ?? null,
  }));

  const lanes = [];
  if (embeddings.length > 0) {
    lanes.push({ key: 'embedding', label: 'Embedding', items: embeddings });
  }
  if (indexes.length > 0) {
    lanes.push({ key: 'index', label: 'Index', items: indexes });
  }

  const memoryKeys: string[] = [];
  for (const memoryKey of ['knowledge', 'graph'] as const) {
    const item = (docStatus.memory ?? []).find(
      candidate => candidate.key === memoryKey
    );
    const key = `memory.${memoryKey}`;
    memoryKeys.push(key);
    lanes.push({
      key,
      label: 'LongMemory',
      items: [
        {
          ...(item ?? {}),
          key,
          label:
            memoryKey === 'knowledge'
              ? 'Извлечение знаний'
              : 'Индекс LongMemory',
          status: getDisplayStatus(item?.status),
        },
      ],
    });
  }
  return {
    pipeline,
    lanes,
    parallel: { after: 'normalize', laneKeys: memoryKeys },
  };
}
