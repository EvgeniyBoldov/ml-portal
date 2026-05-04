import React, { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Modal from '@shared/ui/Modal';
import { useToast } from '@shared/ui/Toast';
import { apiRequest } from '@shared/api/http';
import { buildFileDownloadUrl, buildRagDocFileId } from '@shared/api/files';
import { config } from '@shared/config';
import { openSSE, SSEMessage } from '@shared/lib/sse';
import { useDocumentStatus } from '@shared/api/hooks/useDocumentStatus';
import { PipelineView, PipelineStage, EmbeddingModel } from './PipelineView';
import { StageDetails } from './StageDetails';
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
  
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  const { data: docStatus, isLoading, error } = useDocumentStatus(docId, statusGraphUrl);
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

  // Transform docStatus to pipeline format
  const stages: PipelineStage[] = React.useMemo(() => {
    if (!docStatus?.stages) return [];
    
    const stageOrder: Array<'upload' | 'extract' | 'normalize' | 'chunk'> = ['upload', 'extract', 'normalize', 'chunk'];
    return stageOrder.map(key => {
      const stage = docStatus.stages[key];
      return {
        key,
        label: key.charAt(0).toUpperCase() + key.slice(1),
        status: mapStateToStatus(stage?.state),
        error: stage?.error,
        metrics: stage?.metrics,
        started_at: stage?.started_at,
        finished_at: stage?.finished_at,
      };
    });
  }, [docStatus?.stages]);

  const embeddings: EmbeddingModel[] = React.useMemo(() => {
    if (!docStatus?.embed_models) return [];
    return docStatus.embed_models
      .map(m => ({
        model: m.id || m.name,
        status: mapStateToStatus(m.state),
        version: m.version,
        error: m.error,
        metrics: m.metrics,
        started_at: m.started_at,
        finished_at: m.finished_at,
      }));
  }, [docStatus?.embed_models]);

  const indexes: EmbeddingModel[] = React.useMemo(() => {
    if (!docStatus?.index_models) return [];
    return docStatus.index_models
      .map(m => ({
        model: m.id || m.name,
        status: mapStateToStatus(m.state),
        version: m.version,
        error: m.error,
        metrics: m.metrics,
        started_at: m.started_at,
        finished_at: m.finished_at,
      }));
  }, [docStatus?.index_models]);

  // Get selected stage/model data
  const selectedStageData = React.useMemo(() => {
    if (!selectedStage) return null;
    if (selectedStage === 'embedding' || selectedStage === 'index') return null;
    return stages.find(s => s.key === selectedStage) || null;
  }, [selectedStage, stages]);

  const selectedModelData = React.useMemo(() => {
    if (!selectedModel) return null;
    if (selectedStage === 'embedding') {
      return embeddings.find(e => e.model === selectedModel) || null;
    }
    if (selectedStage === 'index') {
      return indexes.find(i => i.model === selectedModel) || null;
    }
    return null;
  }, [selectedStage, selectedModel, embeddings, indexes]);

  const selectedStageSlug = React.useMemo(() => {
    if (!selectedStage) return null;
    if (selectedStage === 'embedding' && selectedModel) return `embed.${selectedModel}`;
    if (selectedStage === 'index' && selectedModel) return `index.${selectedModel}`;
    if (['upload', 'extract', 'normalize', 'chunk'].includes(selectedStage)) return selectedStage;
    return null;
  }, [selectedStage, selectedModel]);

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
  const handleSelectStage = (stage: string | null, model?: string | null) => {
    setSelectedStage(stage);
    setSelectedModel(model || null);
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
        const response = await apiRequest<{ url: string }>(`${downloadUrlPrefix}?kind=original`);
        window.open(response.url, '_blank');
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
        const response = await apiRequest<{ url: string }>(`${downloadUrlPrefix}?kind=canonical`);
        window.open(response.url, '_blank');
        return;
      }
      const fileId = buildRagDocFileId(docId, 'canonical');
      window.open(buildFileDownloadUrl(fileId), '_blank', 'noopener,noreferrer');
    } catch (error) {
      showToast('Ошибка скачивания', 'error');
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <Modal open={true} onClose={onClose} title="Статус документа" size="xl">
        <div className={styles.loading}>Загрузка...</div>
      </Modal>
    );
  }

  // Error state
  if (error) {
    return (
      <Modal open={true} onClose={onClose} title="Статус документа" size="xl">
        <div className={styles.error}>Не удалось загрузить статус документа</div>
      </Modal>
    );
  }

  const stageType = selectedStage === 'embedding' ? 'embedding' 
    : selectedStage === 'index' ? 'index' 
    : 'pipeline';

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
          <PipelineView
            stages={stages}
            embeddings={embeddings}
            indexes={indexes}
            activeStageSlugs={activeStageSlugs}
            selectedStage={selectedStage}
            selectedModel={selectedModel}
            onSelectStage={handleSelectStage}
          />
        </div>

        {/* Details panel */}
        <div className={styles.detailsSection}>
          <StageDetails
            stage={selectedStageData}
            model={selectedModelData}
            stageType={stageType}
            docId={docId}
            canRestart={canRetrySelectedStage}
            canStop={canStopSelectedStage}
            onRestart={handleRestart}
            onStop={handleStop}
            onDownloadOriginal={handleDownloadOriginal}
            onDownloadNormalized={handleDownloadNormalized}
          />
        </div>
      </div>
    </Modal>
  );
}

function mapStateToStatus(state?: string): 'pending' | 'processing' | 'completed' | 'failed' | 'queued' {
  if (!state) return 'pending';
  switch (state) {
    case 'ok':
    case 'completed':
      return 'completed';
    case 'running':
    case 'processing':
      return 'processing';
    case 'error':
    case 'failed':
      return 'failed';
    case 'queued':
      return 'queued';
    default:
      return 'pending';
  }
}

export default StatusModalNew;
