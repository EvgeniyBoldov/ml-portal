import React from 'react';
import Button from '@shared/ui/Button';
import Badge from '@shared/ui/Badge';
import { Icon } from '@shared/ui/Icon';
import type { PipelineStage, EmbeddingModel, PipelineStageStatus } from './PipelineView';
import styles from './StageDetails.module.css';

interface StageDetailsProps {
  stage: PipelineStage | null;
  model: EmbeddingModel | null;
  stageType: 'pipeline' | 'embedding' | 'index';
  docId: string;
  onRestart?: () => void;
  onDownloadOriginal?: () => void;
  onDownloadNormalized?: () => void;
}

function formatDuration(startedAt?: string | null, finishedAt?: string | null): string {
  if (!startedAt) return '—';
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const duration = (end - start) / 1000;
  
  if (duration < 1) return '<1s';
  if (duration < 60) return `${Math.round(duration)}s`;
  if (duration < 3600) return `${Math.floor(duration / 60)}m ${Math.round(duration % 60)}s`;
  return `${Math.floor(duration / 3600)}h ${Math.floor((duration % 3600) / 60)}m`;
}

function formatDate(date?: string | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function MetricValue({ label, value }: { label: string; value: any }) {
  if (value === null || value === undefined) return null;
  
  let displayValue = value;
  if (typeof value === 'number') {
    displayValue = value.toLocaleString('ru-RU');
  } else if (typeof value === 'boolean') {
    displayValue = value ? 'Да' : 'Нет';
  }

  return (
    <div className={styles.metricRow}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>{displayValue}</span>
    </div>
  );
}

const STATUS_BADGE_VARIANT: Record<PipelineStageStatus, 'default' | 'success' | 'warning' | 'danger'> = {
  pending: 'default',
  queued: 'warning',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
};

const STAGE_LABELS: Record<string, string> = {
  upload: 'Загрузка',
  extract: 'Извлечение текста',
  normalize: 'Нормализация',
  chunk: 'Разбиение на чанки',
  archive: 'Архивация',
  embedding: 'Эмбеддинг',
  index: 'Индексация',
};

const METRIC_LABELS: Record<string, string> = {
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
};

export function StageDetails({
  stage,
  model,
  stageType,
  docId,
  onRestart,
  onDownloadOriginal,
  onDownloadNormalized,
}: StageDetailsProps) {
  const data = model || stage;
  if (!data) {
    return (
      <div className={styles.empty}>
        <Icon name="info" size={24} />
        <p>Выберите этап для просмотра деталей</p>
      </div>
    );
  }

  const status = 'status' in data ? data.status : (data as PipelineStage).status;
  const error = data.error;
  const metrics = data.metrics;
  const startedAt = data.started_at;
  const finishedAt = data.finished_at;

  const title = model 
    ? model.model 
    : STAGE_LABELS[(data as PipelineStage).key] || (data as PipelineStage).key;

  const canRestart = status === 'failed' || status === 'completed';
  const isProcessing = status === 'processing' || status === 'queued';

  // Show download buttons for specific stages
  const showDownloadOriginal = stageType === 'pipeline' && 
    ['upload', 'extract'].includes((data as PipelineStage).key) && 
    status === 'completed';
  const showDownloadNormalized = stageType === 'pipeline' && 
    (data as PipelineStage).key === 'normalize' && 
    status === 'completed';

  return (
    <div className={styles.details}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h3 className={styles.title}>{title}</h3>
          <Badge variant={STATUS_BADGE_VARIANT[status]}>{status}</Badge>
        </div>
        {model?.version && (
          <span className={styles.version}>v{model.version}</span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className={styles.errorBox}>
          <Icon name="alert-triangle" size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Timing */}
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>Время выполнения</h4>
        <div className={styles.timingGrid}>
          <div className={styles.timingItem}>
            <span className={styles.timingLabel}>Начало</span>
            <span className={styles.timingValue}>{formatDate(startedAt)}</span>
          </div>
          <div className={styles.timingItem}>
            <span className={styles.timingLabel}>Окончание</span>
            <span className={styles.timingValue}>{formatDate(finishedAt)}</span>
          </div>
          <div className={styles.timingItem}>
            <span className={styles.timingLabel}>Длительность</span>
            <span className={styles.timingValue}>{formatDuration(startedAt, finishedAt)}</span>
          </div>
        </div>
      </div>

      {/* Metrics */}
      {metrics && Object.keys(metrics).length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>Метрики</h4>
          <div className={styles.metricsGrid}>
            {Object.entries(metrics).map(([key, value]) => (
              <MetricValue 
                key={key} 
                label={METRIC_LABELS[key] || key} 
                value={value} 
              />
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className={styles.actions}>
        {showDownloadOriginal && onDownloadOriginal && (
          <Button variant="secondary" onClick={onDownloadOriginal}>
            <Icon name="download" size={16} />
            Скачать оригинал
          </Button>
        )}
        {showDownloadNormalized && onDownloadNormalized && (
          <Button variant="secondary" onClick={onDownloadNormalized}>
            <Icon name="download" size={16} />
            Скачать JSON
          </Button>
        )}
        {canRestart && onRestart && (
          <Button variant="primary" onClick={onRestart}>
            <Icon name="refresh-cw" size={16} />
            Перезапустить
          </Button>
        )}
        {isProcessing && (
          <div className={styles.processingIndicator}>
            <Icon name="loader" size={16} className={styles.spinner} />
            <span>Выполняется...</span>
          </div>
        )}
      </div>
    </div>
  );
}
