import React, { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Modal from '@shared/ui/Modal';
import { useToast } from '@shared/ui/Toast';
import { apiRequest } from '@shared/api/http';
import { config } from '@shared/config';
import { openSSE, SSEMessage } from '@shared/lib/sse';
import { applyRagEvents } from '@/app/providers/applyRagEvents';
import { useRagDocument } from '@shared/api/hooks/useRagDocuments';
import { PipelineView, PipelineStage, EmbeddingModel } from './PipelineView';
import { StageDetails } from './StageDetails';
import styles from './StatusModalNew.module.css';

interface StatusModalNewProps {
  docId: string;
  docName?: string;
  onClose: () => void;
}

export function StatusModalNew({ docId, docName, onClose }: StatusModalNewProps) {
  const queryClient = useQueryClient();
  const sseRef = useRef<ReturnType<typeof openSSE> | null>(null);
  const { showToast } = useToast();
  
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  const { data: docStatus, isLoading, error } = useRagDocument(docId);

  // SSE subscription for real-time updates
  useEffect(() => {
    const url = `${config.ragEventsUrl}?document_id=${encodeURIComponent(docId)}`;
    const client = openSSE(url, (events: SSEMessage[]) => {
      applyRagEvents(events, queryClient);
    });
    sseRef.current = client;
    return () => {
      if (sseRef.current) {
        sseRef.current.disconnect();
        sseRef.current = null;
      }
    };
  }, [docId, queryClient]);

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
    
    const stageOrder = ['upload', 'extract', 'normalize', 'chunk'];
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
      // Filter out models that were never started (pending without any activity)
      .filter(m => m.state !== 'idle' || m.started_at)
      .map(m => ({
        model: m.id || m.name,
        status: mapStateToStatus(m.state),
        version: m.version,
        error: m.error,
        metrics: (m as any).metrics,
        started_at: m.started_at,
        finished_at: m.finished_at,
      }));
  }, [docStatus?.embed_models]);

  const indexes: EmbeddingModel[] = React.useMemo(() => {
    if (!docStatus?.index_models) return [];
    return docStatus.index_models
      // Filter out models that were never started (pending without any activity)
      .filter(m => m.state !== 'idle' || m.started_at)
      .map(m => ({
        model: m.id || m.name,
        status: mapStateToStatus(m.state),
        version: m.version,
        error: m.error,
        metrics: (m as any).metrics,
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

  // Handlers
  const handleSelectStage = (stage: string | null, model?: string | null) => {
    setSelectedStage(stage);
    setSelectedModel(model || null);
  };

  const handleRestart = async () => {
    if (!selectedStage) return;

    try {
      let stage = selectedStage;
      if (selectedStage === 'embedding' && selectedModel) {
        stage = `embed.${selectedModel}`;
      } else if (selectedStage === 'index' && selectedModel) {
        stage = `index.${selectedModel}`;
      } else if (['upload', 'extract', 'normalize', 'chunk'].includes(selectedStage)) {
        stage = 'extract'; // Restart from extract for pipeline stages
      }

      await apiRequest(`/rag/status/${docId}/ingest/retry?stage=${stage}`, {
        method: 'POST',
        idempotent: true,
      });

      showToast('Перезапуск начат', 'success');
    } catch (error) {
      showToast('Ошибка перезапуска', 'error');
    }
  };

  const handleDownloadOriginal = async () => {
    try {
      const response = await apiRequest<{ url: string }>(`/rag/${docId}/download?kind=original`);
      window.open(response.url, '_blank');
    } catch (error) {
      showToast('Ошибка скачивания', 'error');
    }
  };

  const handleDownloadNormalized = async () => {
    try {
      const response = await apiRequest<{ url: string }>(`/rag/${docId}/download?kind=canonical`);
      window.open(response.url, '_blank');
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
            onRestart={handleRestart}
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
