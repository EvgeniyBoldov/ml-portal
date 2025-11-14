import React from 'react';
import { StageKey, StageStatus, IndexModelStatus } from '../types';
import { StageActions } from './StageActions';
import styles from './StageDetailsPanel.module.css';

interface StageDetailsPanelProps {
  docId: string;
  stage: StageKey;
  status: StageStatus;
  models?: IndexModelStatus[];
  onStart?: () => void;
  onRestart?: () => void;
  onStop?: () => void;
  onRetryModel?: (modelId: string) => void;
}

const STAGE_LABELS: Record<StageKey, string> = {
  upload: 'Upload',
  extract: 'Extract',
  normalize: 'Normalize',
  chunk: 'Chunk',
  index: 'Index',
  archive: 'Archive',
};

export function StageDetailsPanel({
  docId,
  stage,
  status,
  models,
  onStart,
  onRestart,
  onStop,
  onRetryModel,
}: StageDetailsPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h3 className={styles.title}>{STAGE_LABELS[stage]}</h3>
          <span className={[styles.badge, styles[`state-${status.state}`]].join(' ')}>
            {status.state}
          </span>
        </div>
        <div className={styles.headerRight}>
          <StageActions
            stage={stage}
            state={status.state}
            models={models}
            onStart={onStart}
            onRestart={onRestart}
            onStop={onStop}
            onRetryModel={onRetryModel}
          />
        </div>
      </div>

      <div className={styles.content}>
          {/* Meta bar: Started ——— Finished/Updated */}
          <div className={styles.metaBar}>
            <div className={styles.metaItem}>
              Started: {status.started_at ? new Date(status.started_at).toLocaleString() : '—'}
            </div>
            <div className={styles.metaItem}>
              {(() => {
                // prefer finished_at, fallback to updated_at if present on status
                const anyStatus = status as any;
                const finished = status.finished_at;
                const updated = anyStatus.updated_at as string | undefined;
                const label = finished ? 'Finished' : updated ? 'Updated' : 'Finished';
                const value = finished || updated;
                return (
                  <>
                    {label}: {value ? new Date(value).toLocaleString() : '—'}
                  </>
                );
              })()}
            </div>
          </div>

          {/* Timestamps */}
          {/* Дополнительные строки времени больше не дублируем — всё в metaBar */}

          {status.duration_ms && (
            <div className={styles.row}>
              <span className={styles.label}>Duration:</span>
              <span className={styles.value}>{(status.duration_ms / 1000).toFixed(2)}s</span>
            </div>
          )}

          {status.retries !== undefined && status.retries > 0 && (
            <div className={styles.row}>
              <span className={styles.label}>Retries:</span>
              <span className={styles.value}>{status.retries}</span>
            </div>
          )}

          {/* Error */}
          {status.error && (
            <div className={styles.errorBlock}>
              <div className={styles.errorTitle}>ERROR</div>
              <pre className={styles.errorText}>{status.error}</pre>
            </div>
          )}

          {/* Metrics */}
          {status.metrics && Object.keys(status.metrics).length > 0 && (
            <div className={styles.metricsBlock}>
              <div className={styles.metricsTitle}>Metrics:</div>
              {Object.entries(status.metrics).map(([key, value]) => (
                <div key={key} className={styles.row}>
                  <span className={styles.label}>{key}:</span>
                  <span className={styles.value}>{JSON.stringify(value)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Index models list is shown only if multiple models are present */}
          {stage === 'index' && models && models.length > 1 && (
            <div className={styles.modelsBlock}>
              <div className={styles.modelsTitle}>Models</div>
              {models.map((model) => (
                <div key={model.id} className={styles.modelRow}>
                  <span className={styles.modelName}>{model.name}</span>
                  <span className={[styles.badge, styles[`state-${model.state}`]].join(' ')}>
                    {model.state}
                  </span>
                  {model.error && (
                    <div className={styles.modelError}>{model.error}</div>
                  )}
                </div>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}
