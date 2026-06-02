import React from 'react';
import type { BudgetMetric, EntityUsed } from './entityTypes';
import styles from './budget.module.css';

const LABELS: Record<BudgetMetric, string> = {
  planner_steps: 'Step',
  agent_steps: 'Steps',
  tool_calls: 'Calls',
  tokens_in: 'In',
  tokens_out: 'Out',
  tokens_total: 'Tokens',
  retries: 'Retry',
  wall_time_ms: 'Time',
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

function formatSecondsFromMs(ms: number): string {
  return `${(ms / 1000).toFixed(1).replace('.', ',')} s`;
}

export function SpendSummary({ used, metrics }: { used: EntityUsed; metrics?: BudgetMetric[] }): React.ReactElement {
  const keys = metrics ?? Object.keys(used) as BudgetMetric[];
  const rows = keys
    .map((key) => ({ key, value: Number(used[key] ?? 0) }))
    .filter((row) => row.value > 0);

  if (rows.length === 0) {
    return <div className={styles.empty}>Нет расхода</div>;
  }

  return (
    <div className={styles.breakdownTooltip}>
      {rows.map((row) => (
        <div key={row.key} className={styles.breakdownRow}>
          <span>{LABELS[row.key]}</span>
          <span className={styles.number}>
            {row.key === 'wall_time_ms' ? formatSecondsFromMs(row.value) : formatNumber(row.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
