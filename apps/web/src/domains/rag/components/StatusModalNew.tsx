import React, { useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import Modal from '@shared/ui/Modal';
import { useToast } from '@shared/ui/Toast';
import Alert from '@shared/ui/Alert';
import { apiRequest } from '@shared/api/http';
import { ApiError } from '@shared/api/errors';
import type { CollectionCapabilities } from '@shared/api/collections';
import { buildFileDownloadUrl, buildRagDocFileId } from '@shared/api/files';
import { config } from '@shared/config';
import { openSSE, SSEMessage } from '@shared/lib/sse';
import { useDocumentStatus } from '@shared/api/hooks/useDocumentStatus';
import { qk } from '@shared/api/keys';
import {
  StatusFlowDetails,
  StatusFlowView,
  adaptDocumentStatusToFlowModel,
  useStatusFlowSelection,
  type FlowDetailAction,
} from '@shared/components/statusFlow';
import styles from './StatusModalNew.module.css';

function buildDownloadRequestUrl(prefix: string, kind: 'original' | 'canonical', tenantId?: string): string {
  const params = new URLSearchParams({ kind });
  if (tenantId) params.set('tenant_id', tenantId);
  return `${prefix}?${params.toString()}`;
}

interface StatusModalNewProps {
  memoryUrl?: string;
  docId: string;
  docName?: string;
  onClose: () => void;
  /** Override SSE events URL (default: config.ragEventsUrl). Ignored when statusGraphUrl is set — parent owns SSE. */
  sseUrl?: string;
  /** Override status-graph fetch URL (default: /rag/{docId}/status-graph) */
  statusGraphUrl?: string;
  /** Override retry ingest URL prefix (default: /rag/status/{docId}/ingest/retry) */
  retryUrlPrefix?: string;
  /** Override stop ingest URL prefix (default: /rag/status/{docId}/ingest/stop) */
  stopUrlPrefix?: string;
  /** Override download URL prefix (default: /rag/{docId}/download) */
  downloadUrlPrefix?: string;
  tenantId?: string;
  collectionCapabilities?: CollectionCapabilities;
  capabilityReasons?: Record<string, string>;
  onPermissionDenied?: () => void;
}

export function StatusModalNew({
  docId,
  docName,
  onClose,
  sseUrl,
  statusGraphUrl,
  retryUrlPrefix,
  stopUrlPrefix,
  downloadUrlPrefix,
  memoryUrl,
  tenantId,
  collectionCapabilities,
  capabilityReasons,
  onPermissionDenied,
}: StatusModalNewProps) {
  const queryClient = useQueryClient();
  const sseRef = useRef<ReturnType<typeof openSSE> | null>(null);
  const invalidateAtRef = useRef<number>(0);
  const invalidateTimerRef = useRef<number | null>(null);
  const { showToast } = useToast();
  const [permissionError, setPermissionError] = React.useState(false);
  const isCollectionScoped = collectionCapabilities !== undefined;
  const canEditContent = isCollectionScoped ? collectionCapabilities?.can_edit_content === true : true;
  const canIngest = isCollectionScoped ? collectionCapabilities?.can_edit_content === true && collectionCapabilities?.ingest === true : true;
  const canManageMemory = isCollectionScoped ? collectionCapabilities?.can_edit_content === true && collectionCapabilities?.manage_memory === true : true;
  const permissionReason = (key: string) => capabilityReasons?.[key] || 'Операция временно недоступна.';

  const {
    data: docStatus,
    isLoading,
    error,
  } = useDocumentStatus(docId, statusGraphUrl, tenantId);
  const memoryCommand = useMutation({
    mutationFn: (action: 'add' | 'delete') =>
      apiRequest(memoryUrl!, {
        method: action === 'add' ? 'POST' : 'DELETE',
        idempotent: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      showToast('Операция LongMemory поставлена в очередь', 'success');
    },
    onError: error => {
      showToast('Не удалось запустить операцию LongMemory', 'error');
      if (error instanceof ApiError && error.status === 403) {
        setPermissionError(true);
        onPermissionDenied?.();
      }
    },
  });
  const flowModel = React.useMemo(
    () => adaptDocumentStatusToFlowModel(docStatus),
    [docStatus]
  );
  const { selection, setSelection } = useStatusFlowSelection(flowModel);
  const queryKey = React.useMemo(
    () =>
      statusGraphUrl
        ? qk.collections.documentStatus(docId, tenantId)
        : ['document-status', docId],
    [docId, statusGraphUrl, tenantId]
  );

  const scheduleInvalidate = React.useCallback(() => {
    const minIntervalMs = 500;
    const now = Date.now();
    const diff = now - invalidateAtRef.current;
    if (diff >= minIntervalMs) {
      invalidateAtRef.current = now;
      queryClient.invalidateQueries({ queryKey });
      return;
    }

    if (invalidateTimerRef.current != null) {
      return;
    }
    const delay = minIntervalMs - diff;
    invalidateTimerRef.current = window.setTimeout(() => {
      invalidateAtRef.current = Date.now();
      invalidateTimerRef.current = null;
      queryClient.invalidateQueries({ queryKey });
    }, delay);
  }, [queryClient, queryKey]);

  // SSE subscription: open per-document stream for real-time status graph updates.
  // When sseUrl is provided it already points to the dedicated document endpoint.
  // Legacy fallback (config.ragEventsUrl) still appends ?document_id=.
  useEffect(() => {
    const url = sseUrl
      ? sseUrl
      : `${config.ragEventsUrl}?document_id=${encodeURIComponent(docId)}`;
    const client = openSSE(url, (events: SSEMessage[]) => {
      for (const event of events) {
        if (event.type === 'rag.snapshot') {
          const graph = (event.data as Record<string, unknown>)?.graph;
          if (graph) {
            queryClient.setQueryData(queryKey, graph);
          }
          continue;
        }
        scheduleInvalidate();
      }
    });
    sseRef.current = client;
    return () => {
      if (invalidateTimerRef.current != null) {
        window.clearTimeout(invalidateTimerRef.current);
        invalidateTimerRef.current = null;
      }
      if (sseRef.current) {
        sseRef.current.disconnect();
        sseRef.current = null;
      }
    };
  }, [docId, queryClient, queryKey, scheduleInvalidate, sseUrl]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const selectedStageSlug = React.useMemo(() => {
    if (!selection.nodeKey) return null;
    if (selection.laneKey === 'embedding')
      return `embed.${selection.itemKey || selection.nodeKey}`;
    if (selection.laneKey === 'index')
      return `index.${selection.itemKey || selection.nodeKey}`;
    if (['upload', 'extract', 'normalize', 'chunk'].includes(selection.nodeKey))
      return selection.nodeKey;
    return null;
  }, [selection]);

  const selectedRetryStage = React.useMemo(() => {
    if (!selectedStageSlug) return null;
    if (
      ['upload', 'extract', 'normalize', 'chunk'].includes(selectedStageSlug)
    ) {
      return 'extract';
    }
    return selectedStageSlug;
  }, [selectedStageSlug]);

  const controls = React.useMemo(
    () => docStatus?.ingest_policy?.controls || [],
    [docStatus?.ingest_policy?.controls]
  );
  const controlByStage = React.useMemo(
    () => new Map(controls.map(item => [item.stage, item])),
    [controls]
  );
  const activeStageSlugs = docStatus?.ingest_policy?.active_stages || [];

  const canRetrySelectedStage = React.useMemo(() => {
    if (!selectedRetryStage) return false;
    const control = controlByStage.get(selectedRetryStage);
    return Boolean(control?.can_retry);
  }, [controlByStage, selectedRetryStage]);

  const selectedStopStage = React.useMemo(() => {
    if (!selectedStageSlug) return null;
    const selectedControl = controlByStage.get(selectedStageSlug);
    if (selectedControl?.can_stop) {
      return selectedControl.stage;
    }
    if (
      ['upload', 'extract', 'normalize', 'chunk'].includes(selectedStageSlug)
    ) {
      const activePipeline = controls.find(
        item => item.node_type === 'pipeline' && item.can_stop
      );
      return activePipeline?.stage || null;
    }
    return null;
  }, [controlByStage, controls, selectedStageSlug]);

  const canStopSelectedStage = React.useMemo(() => {
    if (!selectedStopStage) return false;
    return Boolean(controlByStage.get(selectedStopStage)?.can_stop);
  }, [controlByStage, selectedStopStage]);

  // Handlers
  const handleSelectStage = (nextSelection: {
    nodeKey: string | null;
    laneKey?: string | null;
    itemKey?: string | null;
  }) => {
    setSelection(nextSelection);
  };

  const handleRestart = React.useCallback(async () => {
    if (!canEditContent) return;
    if (!selectedRetryStage) return;
    if (!canRetrySelectedStage) {
      showToast('Этот этап сейчас нельзя перезапустить', 'error');
      return;
    }

    try {
      const retryBase = retryUrlPrefix || `/rag/status/${docId}/ingest/retry`;
      const params = new URLSearchParams({ stage: selectedRetryStage });
      if (tenantId) params.set('tenant_id', tenantId);
      await apiRequest(`${retryBase}?${params.toString()}`, {
        method: 'POST',
        idempotent: true,
      });

      showToast('Перезапуск начат', 'success');
    } catch (error) {
      showToast('Ошибка перезапуска', 'error');
      if (error instanceof ApiError && error.status === 403) {
        setPermissionError(true);
        onPermissionDenied?.();
      }
    }
  }, [
    canEditContent,
    canRetrySelectedStage,
    docId,
    retryUrlPrefix,
    selectedRetryStage,
    showToast,
    tenantId,
    onPermissionDenied,
  ]);

  const handleStop = React.useCallback(async () => {
    if (!canEditContent) return;
    if (!selectedStopStage || !canStopSelectedStage) {
      showToast('Этот этап сейчас нельзя остановить', 'error');
      return;
    }
    try {
      const stopBase = stopUrlPrefix || `/rag/status/${docId}/ingest/stop`;
      const params = new URLSearchParams({ stage: selectedStopStage });
      if (tenantId) params.set('tenant_id', tenantId);
      await apiRequest(`${stopBase}?${params.toString()}`, {
        method: 'POST',
        idempotent: true,
      });
      showToast('Остановка запрошена', 'success');
    } catch (error) {
      showToast('Ошибка остановки', 'error');
      if (error instanceof ApiError && error.status === 403) {
        setPermissionError(true);
        onPermissionDenied?.();
      }
    }
  }, [
    canEditContent,
    canStopSelectedStage,
    docId,
    selectedStopStage,
    showToast,
    tenantId,
    onPermissionDenied,
    stopUrlPrefix,
  ]);

  const handleDownloadOriginal = React.useCallback(async () => {
    try {
      if (downloadUrlPrefix) {
        const response = await apiRequest<{
          file_id?: string;
          download_url?: string;
        }>(buildDownloadRequestUrl(downloadUrlPrefix, 'original', tenantId));
        const href =
          response.download_url ||
          (response.file_id ? buildFileDownloadUrl(response.file_id) : '');
        if (href) {
          window.open(href, '_blank', 'noopener,noreferrer');
        }
        return;
      }
      const fileId = buildRagDocFileId(docId, 'original');
      window.open(
        buildFileDownloadUrl(fileId),
        '_blank',
        'noopener,noreferrer'
      );
    } catch {
      showToast('Ошибка скачивания', 'error');
    }
  }, [docId, downloadUrlPrefix, showToast, tenantId]);

  const handleDownloadNormalized = React.useCallback(async () => {
    try {
      if (downloadUrlPrefix) {
        const response = await apiRequest<{
          file_id?: string;
          download_url?: string;
        }>(buildDownloadRequestUrl(downloadUrlPrefix, 'canonical', tenantId));
        const href =
          response.download_url ||
          (response.file_id ? buildFileDownloadUrl(response.file_id) : '');
        if (href) {
          window.open(href, '_blank', 'noopener,noreferrer');
        }
        return;
      }
      const fileId = buildRagDocFileId(docId, 'canonical');
      window.open(
        buildFileDownloadUrl(fileId),
        '_blank',
        'noopener,noreferrer'
      );
    } catch {
      showToast('Ошибка скачивания', 'error');
    }
  }, [docId, downloadUrlPrefix, showToast, tenantId]);

  const selectedNode = React.useMemo(() => {
    if (!selection.nodeKey) return null;
    if (selection.laneKey) {
      return (
        flowModel.lanes
          ?.find(lane => lane.key === selection.laneKey)
          ?.items.find(
            item => item.key === (selection.itemKey || selection.nodeKey)
          ) ?? null
      );
    }
    return (
      flowModel.pipeline.find(item => item.key === selection.nodeKey) ?? null
    );
  }, [flowModel, selection]);

  const detailActions = React.useMemo<FlowDetailAction[]>(() => {
    const actions: FlowDetailAction[] = [];
    const showDownloadOriginal =
      !selection.laneKey &&
      ['upload', 'extract'].includes(selection.nodeKey || '') &&
      selectedNode?.status === 'completed';
    const showDownloadNormalized =
      !selection.laneKey &&
      selection.nodeKey === 'normalize' &&
      selectedNode?.status === 'completed';

    if (memoryUrl && canEditContent && !memoryCommand.isPending) {
      const active = (docStatus?.memory ?? []).some(node =>
        ['processing', 'queued'].includes(node.status)
      );
      const removed = (docStatus?.memory ?? []).some(
        node =>
          node.key === 'graph' &&
          node.metrics?.action === 'delete' &&
          node.status === 'completed'
      );
      const failed = (docStatus?.memory ?? []).some(
        node => node.status === 'failed'
      );
      if (
        !active &&
        docStatus?.stages.normalize?.state === 'ok' &&
        (!docStatus.memory?.length || removed || failed)
      ) {
        actions.push({
          key: 'memory-add',
          label: 'Добавить в LongMemory',
          variant: 'outline',
          onClick: () => memoryCommand.mutate('add'),
          disabled: !canManageMemory,
          title: !canManageMemory ? permissionReason('manage_memory') : undefined,
        });
      }
      if (docStatus?.memory?.length && !removed) {
        actions.push({
          key: 'memory-delete',
          label: 'Удалить из LongMemory',
          variant: 'warning',
          onClick: () => memoryCommand.mutate('delete'),
          disabled: !canManageMemory,
          title: !canManageMemory ? permissionReason('manage_memory') : undefined,
        });
      }
    }
    if (showDownloadOriginal) {
      actions.push({
        key: 'download-original',
        label: 'Скачать оригинал',
        icon: 'download',
        variant: 'outline',
        onClick: handleDownloadOriginal,
      });
    }
    if (showDownloadNormalized) {
      actions.push({
        key: 'download-normalized',
        label: 'Скачать JSON',
        icon: 'download',
        variant: 'outline',
        onClick: handleDownloadNormalized,
      });
    }
    if (canStopSelectedStage && canEditContent) {
      actions.push({
        key: 'stop',
        label: 'Остановить',
        icon: 'x',
        variant: 'warning',
        onClick: handleStop,
        disabled: !canIngest,
        title: !canIngest ? permissionReason('ingest') : undefined,
      });
    }
    if (canRetrySelectedStage && canEditContent) {
      actions.push({
        key: 'restart',
        label: 'Перезапустить',
        icon: 'refresh-cw',
        variant: 'primary',
        onClick: handleRestart,
        disabled: !canIngest,
        title: !canIngest ? permissionReason('ingest') : undefined,
      });
    }
    return actions;
  }, [
    selection,
    selectedNode?.status,
    canStopSelectedStage,
    canRetrySelectedStage,
    memoryUrl,
    memoryCommand,
    docStatus,
    handleDownloadNormalized,
    handleDownloadOriginal,
    handleRestart,
    handleStop,
    canEditContent,
    canIngest,
    canManageMemory,
    permissionReason,
  ]);

  const metricLabels = React.useMemo(
    () => ({
      checksum: 'Контрольная сумма',
      encoding: 'Кодировка',
      extractor: 'Экстрактор',
      char_count: 'Символов',
      word_count: 'Слов',
      duration_sec: 'Время (сек)',
      passages: 'Фрагменты документа',
      unique_passages: 'Уникальные фрагменты',
      processed_passages: 'Обработано уникальных фрагментов',
      entities: 'Сущности документа',
      facts: 'Уникальные факты документа',
      extracted_triples: 'Извлечено троек',
      encoded_texts: 'Закодировано текстов в scope',
      reused_vectors: 'Использовано векторов из кеша',
      reused_extraction: 'Использовано сохранённое извлечение',
      scopes_total: 'Индексов scope',
      scopes_completed: 'Готово индексов scope',
      scope_nodes: 'Узлов в обработанных scope',
      scope_edges: 'Связей в обработанных scope',
      scope_slugs: 'Проекты памяти',
      removed_documents: 'Удалено документов',
      added_documents: 'Добавлено документов',
      graphs: 'Графы проектов',
      action: 'Операция',
      skipped: 'Этап пропущен',
      chunk_count: 'Чанков',
      chunk_size_avg: 'Средний размер чанка',
      overlap: 'Перекрытие',
      vector_count: 'Векторов',
      vector_dim: 'Размерность',
      indexed_count: 'Проиндексировано',
    }),
    []
  );

  // Keep all hooks above the loading/error branches. The status query starts
  // in a loading state, and returning before the derived hooks run causes the
  // next render to have a different hook count (React error #310).
  if (isLoading) {
    return (
      <Modal open={true} onClose={onClose} title="Статус документа" size="xl">
        <div className={styles.loading}>Загрузка...</div>
      </Modal>
    );
  }

  if (error) {
    return (
      <Modal open={true} onClose={onClose} title="Статус документа" size="xl">
        <div className={styles.error}>
          Не удалось загрузить статус документа
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={docName || docStatus?.name || 'Статус документа'}
      size="fit"
      className={styles.modal}
      bodyClassName={styles.modalBody}
    >
      <div className={styles.container}>
        {isCollectionScoped && (!canEditContent || permissionError) && (
          <Alert
            variant="warning"
            title="Только просмотр"
            description={permissionError
              ? 'Сервер отклонил изменение прав доступа. Статус обновлён; черновики изменений сохранены.'
              : 'Изменять содержимое могут администраторы и редакторы этой рабочей группы.'}
          />
        )}
        {isCollectionScoped && canEditContent && !canIngest && (
          <Alert variant="warning" title="Управление обработкой временно недоступно" description={permissionReason('ingest')} />
        )}
        {/* Pipeline visualization */}
        <div className={styles.pipelineSection}>
          <StatusFlowView
            model={flowModel}
            activeStageSlugs={activeStageSlugs}
            selection={selection}
            onSelect={handleSelectStage}
          />
        </div>

        {/* Details panel */}
        <div className={styles.detailsSection}>
          <StatusFlowDetails
            node={selectedNode}
            metricLabels={metricLabels}
            actions={detailActions}
          />
        </div>
      </div>
    </Modal>
  );
}

export default StatusModalNew;
