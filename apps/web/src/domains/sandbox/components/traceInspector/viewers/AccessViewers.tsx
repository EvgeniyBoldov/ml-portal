import Badge from '@/shared/ui/Badge';
import { InspectorNotice } from '@/shared/ui/Inspector';
import { accessRows, normalizeLimits } from '../TraceDataViews';
import styles from '../TraceDataViews.module.css';

type LimitRow = ReturnType<typeof normalizeLimits>[number];

const metricValue = (key: string, value: number | undefined): string => {
  if (value === undefined) return '—';
  if (key === 'wall_time_ms') return value >= 1000 ? `${(value / 1000).toFixed(value % 1000 ? 1 : 0)} с` : `${value} мс`;
  return new Intl.NumberFormat('ru-RU').format(value);
};

const limitTone = (row: LimitRow): 'neutral' | 'success' | 'warn' | 'danger' => {
  if (row.limit === undefined) return 'neutral';
  if ((row.used ?? 0) > row.limit || row.remaining === 0) return 'danger';
  return (row.used ?? 0) / row.limit >= 0.8 ? 'warn' : 'success';
};

function LimitsTable({ snapshot, title }: { snapshot: unknown; title: string }) {
  const rows = normalizeLimits(snapshot);
  if (!rows.length) return null;
  return <section className={styles.section}>
    <h4>{title}</h4>
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th>Метрика</th><th>Использовано</th><th>Лимит</th><th>Осталось</th><th>Статус</th></tr></thead>
      <tbody>{rows.map((row) => {
        const tone = limitTone(row);
        const status = row.limit === undefined ? 'Не задан' : tone === 'danger' ? 'Исчерпан' : tone === 'warn' ? 'Близко к лимиту' : 'В норме';
        return <tr key={row.key}><td>{row.label}</td><td>{metricValue(row.key, row.used)}</td><td>{metricValue(row.key, row.limit)}</td><td>{metricValue(row.key, row.remaining)}</td><td><Badge size="small" tone={tone}>{status}</Badge></td></tr>;
      })}</tbody>
    </table></div>
  </section>;
}

export function LimitsViewer({ executorSnapshot, runSnapshot }: { executorSnapshot?: unknown; runSnapshot?: unknown }) {
  const ownRows = normalizeLimits(executorSnapshot);
  const runRows = normalizeLimits(runSnapshot);
  if (!ownRows.length && !runRows.length) return <InspectorNotice tone="neutral" message="Лимиты для этого запуска не записаны в журнал." />;
  return <div className={styles.stack}>
    {ownRows.length ? <LimitsTable snapshot={executorSnapshot} title="Текущий запуск" /> : null}
    {runRows.length ? <LimitsTable snapshot={runSnapshot} title="Общий лимит run" /> : null}
  </div>;
}

const asRecord = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};

export function RbacViewer({ snapshot }: { snapshot?: unknown }) {
  const value = asRecord(snapshot);
  const rbac = asRecord(value.rbac ?? value);
  const rows = accessRows(rbac);
  const collectionFilter = asRecord(rbac.collection_filter);
  const defaultAllow = typeof rbac.default_collection_allow === 'boolean'
    ? rbac.default_collection_allow
    : typeof collectionFilter.default_collection_allow === 'boolean' ? collectionFilter.default_collection_allow : undefined;
  if (!rows.length) return <InspectorNotice tone="neutral" message="RBAC-снимок для этого запуска не записан." />;
  return <div className={styles.stack}>
    {defaultAllow !== undefined ? <InspectorNotice tone={defaultAllow ? 'info' : 'warn'} message={`Коллекции без явного правила: ${defaultAllow ? 'разрешены' : 'запрещены'}.`} /> : null}
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th>Тип</th><th>Сущность</th><th>Доступ</th><th>Причина</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={`${row.kind}:${row.name}:${row.reason}`}><td>{row.kind}</td><td><code>{row.name}</code></td><td><Badge size="small" tone={row.allowed ? 'success' : 'danger'}>{row.allowed ? 'Разрешено' : 'Запрещено'}</Badge></td><td>{row.reason}</td></tr>)}</tbody>
    </table></div>
  </div>;
}

export function hasLimits(snapshot: unknown): boolean { return normalizeLimits(snapshot).length > 0; }
export function hasRbac(snapshot: unknown): boolean {
  const root = asRecord(snapshot);
  return accessRows(asRecord(root.rbac ?? root)).length > 0;
}
