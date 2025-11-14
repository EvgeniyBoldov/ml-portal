import React, { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@shared/api/keys';
import { useRagDocument } from '@shared/api/hooks/useRagDocuments';
import { DocStatus, StageKey, STAGE_ORDER, resetDownstream, StageStatus, aggregateIndexState } from '../types';
import { StagesGraph } from './StagesGraph';
import { StageDetailsPanel } from './StageDetailsPanel';
import Modal from '@shared/ui/Modal';
import { useToast } from '@shared/ui/Toast';
import { idempotencyKey } from '@shared/lib/idempotency';
import { apiRequest } from '@shared/api/http';
import styles from './StatusModal.module.css';

interface StatusModalProps {
  docId: string;
  onClose: () => void;
}

export function StatusModal({ docId, onClose }: StatusModalProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [selectedStage, setSelectedStage] = useState<StageKey | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(undefined);

  // Ensure we actually fetch document detail when modal opens
  const { data: docStatus, isLoading, error } = useRagDocument(docId);

  // Не выбираем этап автоматически — детали откроются только после выбора кружка

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!selectedStage) return;

      const currentIndex = STAGE_ORDER.indexOf(selectedStage);

      if (e.key === 'ArrowLeft' && currentIndex > 0) {
        e.preventDefault();
        setSelectedStage(STAGE_ORDER[currentIndex - 1]);
        setSelectedModelId(undefined);
      } else if (e.key === 'ArrowRight' && currentIndex < STAGE_ORDER.length - 1) {
        e.preventDefault();
        setSelectedStage(STAGE_ORDER[currentIndex + 1]);
        setSelectedModelId(undefined);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedStage, onClose]);

  if (isLoading) {
    return (
      <Modal open={true} onClose={onClose} title={`Status`} size="xl">
        <div style={{ padding: '16px' }}>Загрузка статуса…</div>
      </Modal>
    );
  }

  if (error) {
    return (
      <Modal open={true} onClose={onClose} title={`Status`} size="xl">
        <div style={{ padding: '16px' }}>Не удалось загрузить статус документа</div>
      </Modal>
    );
  }

  if (!docStatus) {
    return null;
  }

  const stages: StageStatus[] = STAGE_ORDER.map((stage) => {
    const stageData = docStatus.stages?.[stage];
    if (!stageData) {
      return { stage, state: 'idle' } as StageStatus;
    }
    return stageData;
  });
  const selectedStatus = selectedStage ? docStatus.stages?.[selectedStage] ?? null : null;

  // Mutation handlers - rely on SSE for updates
  const handleStart = async () => {
    if (!selectedStage) return;

    try {
      // Start full pipeline for any stage
      await apiRequest(`/rag/status/${docId}/ingest/start`, {
        method: 'POST',
        idempotent: true,
      });

      showToast('Пайплайн запущен', 'success');
    } catch (error) {
      showToast('Ошибка запуска пайплайна', 'error');
    }
  };

  const handleRestart = async () => {
    if (!selectedStage) return;

    try {
      // Retry specific stage or full pipeline
      const stage = selectedStage === 'extract' || selectedStage === 'chunk' ? 'extract' : selectedStage;
      await apiRequest(`/rag/status/${docId}/ingest/retry?stage=${stage}`, {
        method: 'POST',
        idempotent: true,
      });

      showToast(`${selectedStage} перезапущен`, 'success');
    } catch (error) {
      showToast(`Ошибка перезапуска ${selectedStage}`, 'error');
    }
  };

  const handleStop = async () => {
    if (!selectedStage) return;

    try {
      // Stop specific stage
      await apiRequest(`/rag/status/${docId}/ingest/stop?stage=${selectedStage}`, {
        method: 'POST',
      });

      showToast(`${selectedStage} остановлен`, 'success');
    } catch (error) {
      showToast(`Ошибка остановки ${selectedStage}`, 'error');
    }
  };

  const handleRetryModel = async (modelId: string) => {
    try {
      // Retry specific embedding model
      await apiRequest(`/rag/status/${docId}/ingest/retry?stage=embed.${modelId}`, {
        method: 'POST',
        idempotent: true,
      });

      showToast(`Модель ${modelId} перезапущена`, 'success');
    } catch (error) {
      showToast(`Ошибка перезапуска модели`, 'error');
    }
  };

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={`Status: ${docStatus.name}`}
      size="xl"
      className={styles.modal}
      bodyClassName={styles.modalBody}
    >
      <div className={[styles.layout, selectedStage ? styles.expanded : styles.collapsed].join(' ')}>
        {/* Left panel: Graph */}
        <div className={styles.graphPanel}>
          <StagesGraph
            stages={stages}
            embedModels={docStatus.embed_models}
            indexModels={docStatus.index_models}
            selected={selectedStage || undefined}
            selectedModelId={selectedModelId}
            onSelect={(stage, modelId) => {
              setSelectedStage(stage);
              setSelectedModelId((stage === 'embedding' || stage === 'index') ? modelId : undefined);
            }}
          />
        </div>

        {/* Right panel: Details */}
        {selectedStage && (
          <div className={styles.detailsPanel}>
            <StageDetailsPanel
              docId={docId}
              stage={selectedStage}
              status={((): StageStatus => {
                if (selectedStage !== 'embedding' && selectedStage !== 'index') return selectedStatus as StageStatus;
                const models = selectedStage === 'embedding' ? (docStatus.embed_models || []) : (docStatus.index_models || []);
                if (selectedModelId) {
                  const m = models.find((mm) => mm.id === selectedModelId);
                  if (m) {
                    return {
                      stage: selectedStage,
                      state: m.state as any,
                      started_at: m.started_at,
                      finished_at: m.finished_at,
                      error: m.error,
                      // @ts-expect-error optional metrics may exist
                      metrics: (m as any).metrics,
                    } as StageStatus;
                  }
                }
                return {
                  stage: selectedStage,
                  state: aggregateIndexState(models),
                  // aggregate level timestamps неочевидны — оставим пустыми
                } as StageStatus;
              })()}
              models={
                (selectedStage === 'embedding' || selectedStage === 'index')
                  ? (selectedModelId
                      ? (selectedStage === 'embedding'
                          ? docStatus.embed_models?.filter((m) => m.id === selectedModelId)
                          : docStatus.index_models?.filter((m) => m.id === selectedModelId))
                      : (selectedStage === 'embedding' ? docStatus.embed_models : docStatus.index_models))
                  : undefined
              }
              onStart={handleStart}
              onRestart={handleRestart}
              onStop={handleStop}
              onRetryModel={handleRetryModel}
            />
          </div>
        )}
      </div>
    </Modal>
  );
}
