import React from 'react';
import Badge from '@/shared/ui/Badge';
import { Tooltip } from '@/shared/ui';
import { Table, TableColumn } from '@/shared/ui/Table';
import type { BudgetMetric, EntityLimits, EntityUsed } from './entityTypes';
import styles from './budget.module.css';

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

function formatValue(n: number, unit = ''): string {
  return `${formatNumber(n)}${unit ? ` ${unit}` : ''}`;
}

function percentUsed(used: number, limit?: number): number | null {
  if (limit === undefined || limit <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
}

function toneForPercent(pct: number | null): 'neutral' | 'warn' | 'danger' {
  if (pct === null) return 'neutral';
  if (pct >= 90) return 'danger';
  if (pct >= 60) return 'warn';
  return 'neutral';
}

const LABELS: Record<BudgetMetric, string> = {
  planner_steps: 'Planner steps',
  agent_steps: 'Agent steps',
  tool_calls: 'Tool calls',
  tokens_in: 'Tokens in',
  tokens_out: 'Tokens out',
  tokens_total: 'Tokens total',
  retries: 'Retries',
  wall_time_ms: 'Wall time',
};

const HINTS: Record<BudgetMetric, string> = {
  planner_steps: 'Количество шагов планировщика',
  agent_steps: 'Количество шагов цикла агента',
  tool_calls: 'Количество вызовов инструментов',
  tokens_in: 'Входные токены LLM-запросов',
  tokens_out: 'Выходные токены LLM-ответов',
  tokens_total: 'Сумма входных и выходных токенов',
  retries: 'Количество повторных попыток',
  wall_time_ms: 'Затраченное время выполнения',
};

const UNITS: Partial<Record<BudgetMetric, string>> = {
  wall_time_ms: 'ms',
};

interface BudgetPillsProps {
  used?: EntityUsed;
  limits?: EntityLimits | null;
  metrics: BudgetMetric[];
  className?: string;
}

export function BudgetPills({ used, limits, metrics, className = '' }: BudgetPillsProps): React.ReactElement | null {
  const source = used ?? {};
  const items = metrics
    .map((key) => {
      const v = Number(source[key] ?? 0);
      const limit = limits?.[key];
      if (v <= 0 && limit === undefined) return null;
      const pct = percentUsed(v, limit);
      const tone = toneForPercent(pct);
      const label = LABELS[key];
      const value = limit !== undefined ? `${formatNumber(v)}/${formatNumber(limit)}` : `${formatNumber(v)}`;
      return (
        <Tooltip key={key} content={HINTS[key]} position="top" maxWidth={280}>
          <span className={styles.pillContainer}>
            <Badge tone={tone} size="small" className={styles.pill}>
              <span className={styles.pillLabel}>{label}</span>
              <span className={styles.pillValue}>{value}</span>
            </Badge>
          </span>
        </Tooltip>
      );
    })
    .filter(Boolean);

  if (items.length === 0) return null;
  return <span className={[styles.pillsGroup, className].join(' ')}>{items as React.ReactNode[]}</span>;
}

interface BudgetTableRow {
  key: BudgetMetric;
  metric: string;
  hint: string;
  used: number;
  limit?: number;
  pct: number | null;
  unit: string;
}

interface BudgetTableProps {
  title: string;
  used: EntityUsed;
  limits: EntityLimits;
  metrics?: BudgetMetric[];
  className?: string;
}

export function BudgetTable({ title, used, limits, metrics, className = '' }: BudgetTableProps): React.ReactElement {
  const metricList: BudgetMetric[] = metrics ?? [
    'planner_steps',
    'agent_steps',
    'tool_calls',
    'tokens_total',
    'retries',
    'wall_time_ms',
  ];

  const rows: BudgetTableRow[] = metricList
    .filter((key) => limits[key] !== undefined || Number(used[key] ?? 0) > 0)
    .map((key) => {
      const usedValue = Number(used[key] ?? 0);
      const limit = limits[key];
      return {
        key,
        metric: LABELS[key],
        hint: HINTS[key],
        used: usedValue,
        limit,
        pct: percentUsed(usedValue, limit),
        unit: UNITS[key] ?? '',
      };
    });

  const columns: TableColumn<BudgetTableRow>[] = [
    {
      key: 'metric',
      title: 'Метрика',
      render: (_, row) => (
        <Tooltip content={row.hint} position="top" maxWidth={300}>
          <span className={styles.metricHint}>{row.metric}</span>
        </Tooltip>
      ),
    },
    {
      key: 'used',
      title: 'Использовано',
      align: 'right',
      render: (_, row) => <span className={styles.number}>{formatValue(row.used, row.unit)}</span>,
    },
    {
      key: 'limit',
      title: 'Лимит',
      align: 'right',
      render: (_, row) => (
        <span className={styles.number}>{row.limit !== undefined ? formatValue(row.limit, row.unit) : '—'}</span>
      ),
    },
    {
      key: 'pct',
      title: '%',
      align: 'right',
      render: (_, row) => <span className={styles.number}>{row.pct === null ? '—' : `${row.pct}%`}</span>,
    },
    {
      key: 'bar',
      title: 'Бар',
      render: (_, row) => {
        if (row.pct === null) return <span className={styles.emptyCell}>—</span>;
        const tone = toneForPercent(row.pct);
        return (
          <div className={styles.usageCell}>
            <div className={styles.usageTrack}>
              <div
                className={[
                  styles.usageFill,
                  tone === 'danger' ? styles.usageDanger : tone === 'warn' ? styles.usageWarn : styles.usageNeutral,
                ].join(' ')}
                style={{ width: `${row.pct}%` }}
              />
            </div>
          </div>
        );
      },
    },
  ];

  if (rows.length === 0) {
    return <div className={[styles.empty, className].join(' ')}>Нет данных по бюджету</div>;
  }

  return (
    <div className={[styles.tableContainer, className].join(' ')}>
      <div className={styles.tableTitle}>{title}</div>
      <Table columns={columns} data={rows} size="small" rowKey="key" stickyHeader={false} />
    </div>
  );
}

export { percentUsed, toneForPercent, formatNumber };
