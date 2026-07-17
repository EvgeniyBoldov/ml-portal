import React, { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Modal from '@shared/ui/Modal';
import { useToast } from '@shared/ui/Toast';
import { apiRequest } from '@shared/api/http';
import { buildFileDownloadUrl, buildRagDocFileId } from '@shared/api/files';
import { config } from '@shared/config';
import { openSSE, SSEMessage } from '@shared/lib/sse';
import { useDocumentStatus } from '@shared/api/hooks/useDocumentStatus';
import {
  StatusFlowDetails,
  StatusFlowView,
  adaptDocumentStatusToFlowModel,
  useStatusFlowSelection,
  type FlowDetailAction,
} from '@shared/components/statusFlow';
import styles from './StatusModalNew.module.css';

interface StatusModalNewProps {
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
}

export function StatusModalNew({ docId, docName, onClose, sseUrl, statusGraphUrl, retryUrlPrefix, stopUrlPrefix, downloadUrlPrefix }: StatusModalNewProps) {
  const queryClient = useQueryClient();
  const sseRef = useRef<ReturnType<typeof openSSE> | null>(null);
  const invalidateAtRef = useRef<number>(0);
  const invalidateTimerRef = useRef<number | null>(null);
  const { showToast } = useToast();
  
  const { data: docStatus, isLoading, error } = useDocumentStatus(docId, statusGraphUrl);
  const flowModel = React.useMemo(() => adaptDocumentStatusToFlowModel(docStatus), [docStatus]);
  const { selection, setSelection } = useStatusFlowSelection(flowModel);
  const queryKey = React.useMemo(
    () => (statusGraphUrl ? ['collections', 'doc-status', docId] : ['document-status', docId]),
    [docId, statusGraphUrl],
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
    if (selection.laneKey === 'embedding') return `embed.${selection.itemKey || selection.nodeKey}`;
    if (selection.laneKey === 'index') return `index.${selection.itemKey || selection.nodeKey}`;
    if (['upload', 'extract', 'normalize', 'chunk'].includes(selection.nodeKey)) return selection.nodeKey;
    return null;
  }, [selection]);

  const selectedRetryStage = React.useMemo(() => {
    if (!selectedStageSlug) return null;
    if (['upload', 'extract', 'normalize', 'chunk'].includes(selectedStageSlug)) {
      return 'extract';
    }
    return selectedStageSlug;
  }, [selectedStageSlug]);

  const controls = React.useMemo(() => docStatus?.ingest_policy?.controls || [], [docStatus?.ingest_policy?.controls]);
  const controlByStage = React.useMemo(
    () => new Map(controls.map((item) => [item.stage, item])),
    [controls],
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
    if (['upload', 'extract', 'normalize', 'chunk'].includes(selectedStageSlug)) {
      const activePipeline = controls.find((item) => item.node_type === 'pipeline' && item.can_stop);
      return activePipeline?.stage || null;
    }
    return null;
  }, [controlByStage, controls, selectedStageSlug]);

  const canStopSelectedStage = React.useMemo(() => {
    if (!selectedStopStage) return false;
    return Boolean(controlByStage.get(selectedStopStage)?.can_stop);
  }, [controlByStage, selectedStopStage]);

  // Handlers
  const handleSelectStage = (nextSelection: { nodeKey: string | null; laneKey?: string | null; itemKey?: string | null }) => {
    setSelection(nextSelection);
  };

  const handleRestart = async () => {
    if (!selectedRetryStage) return;
    if (!canRetrySelectedStage) {
      showToast('Этот этап сейчас нельзя перезапустить', 'error');
      return;
    }

    try {
      const retryBase = retryUrlPrefix || `/rag/status/${docId}/ingest/retry`;
      await apiRequest(`${retryBase}?stage=${selectedRetryStage}`, {
        method: 'POST',
        idempotent: true,
      });

      showToast('Перезапуск начат', 'success');
    } catch (error) {
      showToast('Ошибка перезапуска', 'error');
    }
  };

  const handleStop = async () => {
    if (!selectedStopStage || !canStopSelectedStage) {
      showToast('Этот этап сейчас нельзя остановить', 'error');
      return;
    }
    try {
      const stopBase = stopUrlPrefix || `/rag/status/${docId}/ingest/stop`;
      await apiRequest(`${stopBase}?stage=${selectedStopStage}`, {
        method: 'POST',
        idempotent: true,
      });
      showToast('Остановка запрошена', 'success');
    } catch {
      showToast('Ошибка остановки', 'error');
    }
  };

  const handleDownloadOriginal = async () => {
    try {
      if (downloadUrlPrefix) {
        const response = await apiRequest<{ file_id?: string; download_url?: string }>(`${downloadUrlPrefix}?kind=original`);
        const href = response.download_url || (response.file_id ? buildFileDownloadUrl(response.file_id) : '');
        if (href) {
          window.open(href, '_blank', 'noopener,noreferrer');
        }
        return;
      }
      const fileId = buildRagDocFileId(docId, 'original');
      window.open(buildFileDownloadUrl(fileId), '_blank', 'noopener,noreferrer');
    } catch (error) {
      showToast('Ошибка скачивания', 'error');
    }
  };

  const handleDownloadNormalized = async () => {
    try {
      if (downloadUrlPrefix) {
        const response = await apiRequest<{ file_id?: string; download_url?: string }>(`${downloadUrlPrefix}?kind=canonical`);
        const href = response.download_url || (response.file_id ? buildFileDownloadUrl(response.file_id) : '');
        if (href) {
          window.open(href, '_blank', 'noopener,noreferrer');
        }
        return;
      }
      const fileId = buildRagDocFileId(docId, 'canonical');
      window.open(buildFileDownloadUrl(fileId), '_blank', 'noopener,noreferrer');
    } catch (error) {
      showToast('Ошибка скачивания', 'error');
    }
  };

  const selectedNode = React.useMemo(() => {
    if (!selection.nodeKey) return null;
    if (selection.laneKey) {
      return flowModel.lanes?.find((lane) => lane.key === selection.laneKey)?.items.find((item) => item.key === (selection.itemKey || selection.nodeKey)) ?? null;
    }
    return flowModel.pipeline.find((item) => item.key === selection.nodeKey) ?? null;
  }, [flowModel, selection]);

  const detailActions = React.useMemo<FlowDetailAction[]>(() => {
    const actions: FlowDetailAction[] = [];
    const showDownloadOriginal = !selection.laneKey && ['upload', 'extract'].includes(selection.nodeKey || '') && selectedNode?.status === 'completed';
    const showDownloadNormalized = !selection.laneKey && selection.nodeKey === 'normalize' && selectedNode?.status === 'completed';

    if (showDownloadOriginal) {
      actions.push({ key: 'download-original', label: 'Скачать оригинал', icon: 'download', variant: 'outline', onClick: handleDownloadOriginal });
    }
    if (showDownloadNormalized) {
      actions.push({ key: 'download-normalized', label: 'Скачать JSON', icon: 'download', variant: 'outline', onClick: handleDownloadNormalized });
    }
    if (canStopSelectedStage) {
      actions.push({ key: 'stop', label: 'Остановить', icon: 'x', variant: 'warning', onClick: handleStop });
    }
    if (canRetrySelectedStage) {
      actions.push({ key: 'restart', label: 'Перезапустить', icon: 'refresh-cw', variant: 'primary', onClick: handleRestart });
    }
    return actions;
  }, [selection, selectedNode?.status, canStopSelectedStage, canRetrySelectedStage]);

  const metricLabels = React.useMemo(() => ({
    checksum: 'Контрольная сумма',
    encoding: 'Кодировка',
    extractor: 'Экстрактор',
    char_count: 'Символов',
    word_count: 'Слов',
    duration_sec: 'Время (сек)',
    chunk_count: 'Чанков',
    chunk_size_avg: 'Средний размер чанка',
    overlap: 'Перекрытие',
    vector_count: 'Векторов',
    vector_dim: 'Размерность',
    indexed_count: 'Проиндексировано',
  }), []);

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
        <div className={styles.error}>Не удалось загрузить статус документа</div>
      </Modal>
    );
  }

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={docName || docStatus?.name || 'Статус документа'}
      size="xl"
      className={styles.modal}
    >
      <div className={styles.container}>
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
