import React from 'react';

import Badge from '@shared/ui/Badge';
import Button from '@shared/ui/Button';
import { Icon } from '@shared/ui/Icon';

import type { FlowDetailAction, FlowDetailItem, FlowNode, FlowStatus } from './types';
import { getStatusTone } from './statusFlowUtils';
import styles from './StatusFlowDetails.module.css';

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

function MetricValue({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  let displayValue: string | number | boolean = value as string | number | boolean;
  if (typeof value === 'number') {
    displayValue = value.toLocaleString('ru-RU');
  } else if (typeof value === 'boolean') {
    displayValue = value ? 'Да' : 'Нет';
  } else if (Array.isArray(value)) {
    displayValue = value.join(', ');
  } else if (typeof value === 'object') {
    displayValue = JSON.stringify(value);
  }

  return (
    <div className={styles.metricRow}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>{String(displayValue)}</span>
    </div>
  );
}

export function StatusFlowDetails({
  node,
  emptyText = 'Выберите этап для просмотра деталей',
  statusLabel,
  infoItems = [],
  metricLabels = {},
  actions = [],
  processingText = 'Выполняется...',
}: {
  node: FlowNode | null;
  emptyText?: string;
  statusLabel?: string;
  infoItems?: FlowDetailItem[];
  metricLabels?: Record<string, string>;
  actions?: FlowDetailAction[];
  processingText?: string;
}) {
  if (!node) {
    return (
      <div className={styles.empty}>
        <Icon name="info" size={24} />
        <p>{emptyText}</p>
      </div>
    );
  }

  const isProcessing = node.status === 'processing' || node.status === 'queued';

  return (
    <div className={styles.details}>
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h3 className={styles.title}>{node.label}</h3>
          <Badge tone={getStatusTone(node.status as FlowStatus)}>{statusLabel || node.status}</Badge>
        </div>
        {node.version ? <span className={styles.version}>v{node.version}</span> : null}
      </div>

      {node.error ? (
        <div className={styles.errorBox}>
          <Icon name="alert-triangle" size={16} />
          <span>{node.error}</span>
        </div>
      ) : null}

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>Время выполнения</h4>
        <div className={styles.timingGrid}>
          <div className={styles.timingItem}>
            <span className={styles.timingLabel}>Начало</span>
            <span className={styles.timingValue}>{formatDate(node.started_at)}</span>
          </div>
          <div className={styles.timingItem}>
            <span className={styles.timingLabel}>Окончание</span>
            <span className={styles.timingValue}>{formatDate(node.finished_at)}</span>
          </div>
          <div className={styles.timingItem}>
            <span className={styles.timingLabel}>Длительность</span>
            <span className={styles.timingValue}>{formatDuration(node.started_at, node.finished_at)}</span>
          </div>
        </div>
      </div>

      {!node.error && infoItems.length > 0 ? (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>Информация</h4>
          <div className={styles.metricsGrid}>
            {infoItems.map((item) => (
              <MetricValue key={`${item.label}-${item.value}`} label={item.label} value={item.value} />
            ))}
          </div>
        </div>
      ) : null}

      {node.metrics && Object.keys(node.metrics).length > 0 ? (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>Метрики</h4>
          <div className={styles.metricsGrid}>
            {Object.entries(node.metrics).map(([key, value]) => (
              <MetricValue key={key} label={metricLabels[key] || key} value={value} />
            ))}
          </div>
        </div>
      ) : null}

      <div className={styles.actions}>
        {actions.map((action) => (
          <Button key={action.key} variant={action.variant || 'outline'} onClick={action.onClick}>
            {action.icon ? <Icon name={action.icon} size={16} /> : null}
            {action.label}
          </Button>
        ))}
        {isProcessing ? (
          <div className={styles.processingIndicator}>
            <Icon name="loader" size={16} className={styles.spinner} />
            <span>{processingText}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default StatusFlowDetails;
