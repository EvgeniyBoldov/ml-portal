import Badge from '@/shared/ui/Badge';
import { InspectorNotice } from '@/shared/ui/Inspector';
import type { TraceAccessView, TraceLimitsView } from '../../../traceProjection';
import { InspectorEmptyState, InspectorSection, InspectorStack, InspectorTable } from '../InspectorPrimitives';

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
  return <InspectorSection title={title}>
    <InspectorTable headers={['Метрика', 'Использовано', 'Лимит', 'Осталось', 'Статус']}>
      {view.rows.map((row) => {
        const tone = limitTone(row);
        const status = row.status === 'neutral' ? 'Не задан' : row.status === 'exceeded' ? 'Исчерпан' : row.status === 'warning' ? 'Близко к лимиту' : 'В норме';
        return <tr key={row.key}><td>{row.label}</td><td>{metricValue(row.key, row.used)}</td><td>{metricValue(row.key, row.limit)}</td><td>{metricValue(row.key, row.remaining)}</td><td><Badge size="small" tone={tone}>{status}</Badge></td></tr>;
      })}
    </InspectorTable>
  </InspectorSection>;
}

export function LimitsViewer({ limits }: { limits?: TraceLimitsView }) {
  if (!limits?.rows.length) return <InspectorEmptyState message="Локальные ограничения для этого исполнителя не записаны в журнал." />;
  return <InspectorStack><LimitsTable view={limits} title="Ограничения исполнителя" /></InspectorStack>;
}

export function RbacViewer({ access }: { access?: TraceAccessView }) {
  if (!access) return <InspectorEmptyState message="RBAC-снимок для этого запуска не записан." />;
  if (!access.rows.length && access.defaultCollectionAllow === undefined) return <InspectorEmptyState message="RBAC-снимок не содержит решений доступа." />;
  return <InspectorStack>
    {access.defaultCollectionAllow !== undefined ? <InspectorNotice tone={access.defaultCollectionAllow ? 'info' : 'warn'} message={`Коллекции без явного правила: ${access.defaultCollectionAllow ? 'разрешены' : 'запрещены'}.`} /> : null}
    {access.rows.length ? <InspectorTable headers={['Тип', 'Сущность', 'Доступ', 'Причина']}>
      {access.rows.map((row) => <tr key={`${row.kind}:${row.name}:${row.reason}`}><td>{row.kind}</td><td><code>{row.name}</code></td><td><Badge size="small" tone={row.allowed ? 'success' : 'danger'}>{row.allowed ? 'Разрешено' : 'Запрещено'}</Badge></td><td>{row.reason}</td></tr>)}
    </InspectorTable> : null}
  </InspectorStack>;
}
