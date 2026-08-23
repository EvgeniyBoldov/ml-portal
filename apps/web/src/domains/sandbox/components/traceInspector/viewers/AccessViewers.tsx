import Badge from '@/shared/ui/Badge';
import { InspectorNotice } from '@/shared/ui/Inspector';
import type { TraceAccessView, TraceLimitsView } from '../../../traceProjection';
import styles from '../TraceDataViews.module.css';

type LimitRow = TraceLimitsView['rows'][number];

const metricValue = (key: string, value: number | undefined): string => {
  if (value === undefined) return '—';
  if (key === 'wall_time_ms') return value >= 1000 ? `${(value / 1000).toFixed(value % 1000 ? 1 : 0)} с` : `${value} мс`;
  return new Intl.NumberFormat('ru-RU').format(value);
};

const limitTone = (row: LimitRow): 'neutral' | 'success' | 'warn' | 'danger' => ({
  neutral: 'neutral', ok: 'success', warning: 'warn', exceeded: 'danger',
}[row.status] as 'neutral' | 'success' | 'warn' | 'danger');

function LimitsTable({ view, title }: { view: TraceLimitsView; title: string }) {
  if (!view.rows.length) return null;
  return <section className={styles.section}>
    <h4>{title}</h4>
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th>Метрика</th><th>Использовано</th><th>Лимит</th><th>Осталось</th><th>Статус</th></tr></thead>
      <tbody>{view.rows.map((row) => {
        const tone = limitTone(row);
        const status = row.status === 'neutral' ? 'Не задан' : row.status === 'exceeded' ? 'Исчерпан' : row.status === 'warning' ? 'Близко к лимиту' : 'В норме';
        return <tr key={row.key}><td>{row.label}</td><td>{metricValue(row.key, row.used)}</td><td>{metricValue(row.key, row.limit)}</td><td>{metricValue(row.key, row.remaining)}</td><td><Badge size="small" tone={tone}>{status}</Badge></td></tr>;
      })}</tbody>
    </table></div>
  </section>;
}

export function LimitsViewer({ executorLimits, runLimits }: { executorLimits?: TraceLimitsView; runLimits?: TraceLimitsView }) {
  if (!executorLimits?.rows.length && !runLimits?.rows.length) return <InspectorNotice tone="neutral" message="Лимиты для этого запуска не записаны в журнал." />;
  return <div className={styles.stack}>
    {executorLimits ? <LimitsTable view={executorLimits} title="Текущий запуск" /> : null}
    {runLimits ? <LimitsTable view={runLimits} title="Общий лимит run" /> : null}
  </div>;
}

export function RbacViewer({ access }: { access?: TraceAccessView }) {
  if (!access) return <InspectorNotice tone="neutral" message="RBAC-снимок для этого запуска не записан." />;
  if (!access.rows.length && access.defaultCollectionAllow === undefined) return <InspectorNotice tone="neutral" message="RBAC-снимок не содержит решений доступа." />;
  return <div className={styles.stack}>
    {access.defaultCollectionAllow !== undefined ? <InspectorNotice tone={access.defaultCollectionAllow ? 'info' : 'warn'} message={`Коллекции без явного правила: ${access.defaultCollectionAllow ? 'разрешены' : 'запрещены'}.`} /> : null}
    {access.rows.length ? <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th>Тип</th><th>Сущность</th><th>Доступ</th><th>Причина</th></tr></thead>
      <tbody>{access.rows.map((row) => <tr key={`${row.kind}:${row.name}:${row.reason}`}><td>{row.kind}</td><td><code>{row.name}</code></td><td><Badge size="small" tone={row.allowed ? 'success' : 'danger'}>{row.allowed ? 'Разрешено' : 'Запрещено'}</Badge></td><td>{row.reason}</td></tr>)}</tbody>
    </table></div> : null}
  </div>;
}
