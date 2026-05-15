/**
 * Budget UI Components
 *
 * BudgetPill — compact metric display on trace cards
 * BudgetTable — full budget breakdown in Inspector
 */

import React from 'react';
import Badge from '@/shared/ui/Badge';
import { Table, TableColumn } from '@/shared/ui/Table';
import type { BudgetDelta, BudgetMetric, BudgetSnapshot } from './entityTypes';
import styles from './budget.module.css';

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

function percentUsed(used: number, limit?: number): number | null {
  if (limit === undefined || limit === 0) return null;
  return Math.min(100, Math.round((used / limit) * 100));
}

function toneForPercent(pct: number | null): 'neutral' | 'warn' | 'danger' {
  if (pct === null) return 'neutral';
  if (pct > 85) return 'danger';
  if (pct > 60) return 'warn';
  return 'neutral';
}

// ------------------------------------------------------------------
// Labels / descriptions
// ------------------------------------------------------------------

const LABELS: Record<string, string> = {
  steps: 'Степы',
  tools: 'Вызовы',
  retries: 'Ретраи',
  tokens: 'Токены',
  wallTimeMs: 'Время',
};

const UNITS: Record<string, string> = {
  steps: '',
  tools: '',
  retries: '',
  tokens: '',
  wallTimeMs: 'ms',
};

const DESCRIPTIONS: Record<string, string> = {
  steps: 'Сколько шагов рантайма потрачено',
  tools: 'Сколько вызовов инструментов потрачено',
  retries: 'Сколько повторных попыток потрачено',
  tokens: 'Сколько токенов израсходовано',
  wallTimeMs: 'Сколько времени выполнения потрачено',
};

// ------------------------------------------------------------------
// Budget Pill
// ------------------------------------------------------------------

interface BudgetPillProps {
  metric: BudgetMetric;
  metricKey?: 'steps' | 'tools' | 'retries' | 'tokens' | 'wallTimeMs';
  label: string;
  unit?: string;
  showLimit?: boolean;
  mode?: 'delta' | 'total';
  className?: string;
}

export function BudgetPill({
  metric,
  metricKey,
  label,
  unit = '',
  showLimit = true,
  mode = 'total',
  className = '',
}: BudgetPillProps): React.ReactElement {
  const pct = percentUsed(metric.used, metric.limit);
  const tone = toneForPercent(pct);
  const description = metricKey ? DESCRIPTIONS[metricKey] : '';

  const usage = metric.limit !== undefined
    ? `${formatNumber(metric.used)} из ${formatNumber(metric.limit)}${unit ? ` ${unit}` : ''}`
    : `${formatNumber(metric.used)}${unit ? ` ${unit}` : ''}`;

  const tooltip = [
    `${label}: ${usage}`,
    pct !== null ? `${pct}% лимита` : 'Лимит не задан',
    description,
  ].filter(Boolean).join(' • ');

  const display = mode === 'delta'
    ? `+${formatNumber(metric.used)}${unit ? ` ${unit}` : ''}`
    : showLimit && metric.limit !== undefined
      ? `${formatNumber(metric.used)}/${formatNumber(metric.limit)}${unit ? unit[0] : ''}`
      : `${formatNumber(metric.used)}${unit ? unit[0] : ''}`;

  return (
    <span className={[styles.pillContainer, className].join(' ')} title={tooltip}>
      <Badge tone={tone} size="small" className={styles.pill}>
        <span className={styles.pillLabel}>{label}</span>
        <span className={styles.pillValue}>{display}</span>
      </Badge>
    </span>
  );
}

// ------------------------------------------------------------------
// Budget Pills Group (for trace cards)
// ------------------------------------------------------------------

interface BudgetPillsProps {
  snapshot?: BudgetSnapshot;
  delta?: BudgetDelta;
  kinds: Array<'steps' | 'tools' | 'retries' | 'tokens' | 'wallTimeMs'>;
  className?: string;
}

export function BudgetPills({
  snapshot,
  delta,
  kinds,
  className = '',
}: BudgetPillsProps): React.ReactElement | null {
  const source = delta ?? snapshot;
  const mode: 'delta' | 'total' = delta ? 'delta' : 'total';
  if (!source) return null;

  const pills = kinds
    .filter((kind) => {
      const metric = source[kind];
      return metric && metric.used > 0;
    })
    .map((kind) => {
      const metric = source[kind]!;
      return (
        <BudgetPill
          key={kind}
          metric={metric}
          metricKey={kind}
          label={LABELS[kind]}
          unit={UNITS[kind]}
          showLimit={metric.limit !== undefined}
          mode={mode}
        />
      );
    });

  if (pills.length === 0) return null;

  return (
    <span className={[styles.pillsGroup, className].join(' ')}>
      {pills}
    </span>
  );
}

// ------------------------------------------------------------------
// Budget Table (for Inspector tab)
// ------------------------------------------------------------------

interface BudgetTableRow {
  key: string;
  metric: string;
  entityUsed: number;
  totalUsed: number;
  limit?: number;
  unit: string;
  pctTotal: number | null;
}

interface BudgetTableProps {
  snapshot?: BudgetSnapshot;
  delta?: BudgetDelta;
  title?: string;
  className?: string;
}

function hasConsumedBudget(source?: BudgetSnapshot | BudgetDelta): boolean {
  if (!source) return false;
  const metrics = [source.steps, source.tools, source.retries, source.tokens, source.wallTimeMs];
  return metrics.some((metric) => typeof metric?.used === 'number' && metric.used > 0);
}

function metricOf(
  source: BudgetSnapshot | BudgetDelta | undefined,
  key: keyof BudgetSnapshot,
): BudgetMetric | undefined {
  return source?.[key];
}

function formatValue(value: number, unit: string): string {
  return `${formatNumber(value)}${unit ? ` ${unit}` : ''}`;
}

export function BudgetTable({
  snapshot,
  delta,
  title = 'Использование бюджета',
  className = '',
}: BudgetTableProps): React.ReactElement | null {
  if (!snapshot && !delta) {
    return (
      <div className={[styles.empty, className].join(' ')}>
        Нет данных по бюджету
      </div>
    );
  }

  const rows: BudgetTableRow[] = [];

  const addRow = (key: keyof BudgetSnapshot, unit: string) => {
    const totalMetric = metricOf(snapshot, key);
    const entityMetric = metricOf(delta, key);
    const totalUsed = Math.max(0, totalMetric?.used ?? 0);
    const entityUsed = Math.max(0, entityMetric?.used ?? totalUsed);
    const limit = totalMetric?.limit ?? entityMetric?.limit;

    if (entityUsed <= 0 && totalUsed <= 0) return;

    rows.push({
      key,
      metric: LABELS[key] ?? String(key),
      entityUsed,
      totalUsed,
      limit,
      unit,
      pctTotal: percentUsed(totalUsed, limit),
    });
  };

  addRow('steps', '');
  addRow('tools', '');
  addRow('retries', '');
  addRow('tokens', '');
  addRow('wallTimeMs', 'ms');

  if (rows.length === 0) {
    return (
      <div className={[styles.empty, className].join(' ')}>
        Нет данных по бюджету
      </div>
    );
  }

  const columns: TableColumn<BudgetTableRow>[] = [
    {
      key: 'metric',
      title: 'Метрика',
      dataIndex: 'metric',
    },
    {
      key: 'entity',
      title: 'Сущность',
      align: 'right',
      render: (_, row) => (
        <span className={styles.number}>
          {formatValue(row.entityUsed, row.unit)}
        </span>
      ),
    },
    {
      key: 'total',
      title: 'Всего',
      align: 'right',
      render: (_, row) => (
        <span className={styles.number}>
          {formatValue(row.totalUsed, row.unit)}
        </span>
      ),
    },
    {
      key: 'limit',
      title: 'Лимит',
      align: 'right',
      render: (_, row) => (
        <span className={styles.number}>
          {row.limit !== undefined ? formatValue(row.limit, row.unit) : '—'}
        </span>
      ),
    },
    {
      key: 'pct',
      title: 'Использование',
      align: 'right',
      render: (_, row) => {
        if (row.pctTotal === null) return <span className={styles.emptyCell}>—</span>;
        const tone = toneForPercent(row.pctTotal);
        return (
          <div className={styles.usageCell}>
            <div className={styles.usageTrack}>
              <div
                className={[
                  styles.usageFill,
                  tone === 'danger' ? styles.usageDanger : tone === 'warn' ? styles.usageWarn : styles.usageNeutral,
                ].join(' ')}
                style={{ width: `${row.pctTotal}%` }}
              />
            </div>
            <Badge tone={tone} size="small" className={styles.pctBadge}>
              {row.pctTotal}%
            </Badge>
          </div>
        );
      },
    },
  ];

  return (
    <div className={[styles.tableContainer, className].join(' ')}>
      <div className={styles.tableTitle}>{title}</div>
      <Table
        columns={columns}
        data={rows}
        size="small"
        rowKey="key"
        stickyHeader={false}
      />
    </div>
  );
}

// ------------------------------------------------------------------
// Budget Helpers
// ------------------------------------------------------------------

export {
  percentUsed,
  toneForPercent,
  formatNumber,
};
