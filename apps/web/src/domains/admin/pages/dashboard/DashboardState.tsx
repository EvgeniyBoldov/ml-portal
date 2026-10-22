import React from 'react';
import { Badge } from '@/shared/ui';
import { number } from './format';
import styles from './DashboardTables.module.css';

const status: Record<
  string,
  { label: string; tone: 'success' | 'danger' | 'warn' | 'neutral' }
> = {
  healthy: { label: 'Доступна', tone: 'success' },
  ready: { label: 'Готов', tone: 'success' },
  unavailable: { label: 'Недоступна', tone: 'danger' },
  unhealthy: { label: 'Недоступна', tone: 'danger' },
  degraded: { label: 'Сбой проверки', tone: 'warn' },
  absent: { label: 'Нет индекса', tone: 'neutral' },
  unknown: { label: 'Неизвестно', tone: 'neutral' },
};

export function State({ value }: { value: string }) {
  const item = status[value] ?? status.unknown;
  return <Badge tone={item.tone}>{item.label}</Badge>;
}

export function Progress({
  ready,
  processing,
  failed,
  partial,
}: {
  ready?: number;
  processing: number;
  failed: number;
  partial?: number;
}) {
  return (
    <div className={styles.progress}>
      {ready !== undefined && (
        <span title="Готово">
          <Badge tone="success">{number(ready)}</Badge>
        </span>
      )}
      <span title="В обработке">
        <Badge tone="info">{number(processing)}</Badge>
      </span>
      {partial !== undefined && (
        <span title="Частично готовы">
          <Badge tone="warn">{number(partial)}</Badge>
        </span>
      )}
      <span title="С ошибкой">
        <Badge tone={failed ? 'danger' : 'neutral'}>{number(failed)}</Badge>
      </span>
    </div>
  );
}
