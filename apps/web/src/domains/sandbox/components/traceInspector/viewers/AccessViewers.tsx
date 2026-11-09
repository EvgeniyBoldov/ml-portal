import Badge from '@/shared/ui/Badge';
import { InspectorNotice } from '@/shared/ui/Inspector';
import styles from './AccessSnapshotViewer.module.css';
import type { TraceAccessItem, TraceAccessSnapshot, TraceAccessView, TraceExecutorStatistic, TraceLimitsView } from '../../../traceProjection';
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

function LimitsTable({ view, title, agentCompact = false }: { view: TraceLimitsView; title: string; agentCompact?: boolean }) {
  if (!view.rows.length) return null;
  return <InspectorSection title={title}>
    <InspectorTable compact={agentCompact} headers={agentCompact ? ['Параметр', 'Расход', 'Лимит'] : ['Метрика', 'Использовано', 'Лимит', 'Осталось', 'Статус']}>
      {view.rows.map((row) => {
        const tone = limitTone(row);
        const status = row.status === 'neutral' ? 'Не задан' : row.status === 'exceeded' ? 'Исчерпан' : row.status === 'warning' ? 'Близко к лимиту' : 'В норме';
        if (agentCompact) {
          const used = row.used;
          const limit = row.limit;
          const usageStatus = used === undefined || limit === undefined ? undefined
            : used > limit ? 'Перерасход'
              : used === limit ? 'Лимит достигнут'
                : row.status === 'warning' ? 'Близко к лимиту' : 'В норме';
          const overage = used !== undefined && limit !== undefined && used > limit ? used - limit : undefined;
          const remaining = used !== undefined && limit !== undefined && used <= limit
            ? Math.max(0, limit - used) : row.remaining;
          const showUsageBar = used !== undefined && limit !== undefined && limit > 0;
          const usagePercent = showUsageBar ? Math.min(100, Math.max(0, (used / limit) * 100)) : undefined;
          const statusTone = usageStatus === 'Перерасход' || usageStatus === 'Лимит достигнут' ? 'danger'
            : usageStatus === 'Близко к лимиту' ? 'warn' : 'success';
          return <tr key={row.key}>
            <td>
              <div className={styles.limitLabel}><span>{row.label}</span>{usageStatus && usageStatus !== 'В норме' ? <Badge size="small" tone={statusTone}>{usageStatus}</Badge> : null}</div>
            </td>
            <td>
              <div className={styles.limitUsage}>
                <span>{used === undefined ? 'Расход не записан' : metricValue(row.key, used)}</span>
                {showUsageBar && usagePercent !== undefined ? <progress className={styles.usageBar} data-tone={statusTone} max={100} value={usagePercent} aria-label={`Использование лимита: ${row.label}`} /> : null}
                {overage !== undefined ? <span className={styles.usageDetail}>Перерасход: +{metricValue(row.key, overage)}</span>
                  : used !== undefined && limit !== undefined && remaining !== undefined ? <span className={styles.usageDetail}>Остаток: {metricValue(row.key, remaining)}</span>
                    : row.remaining !== undefined ? <span className={styles.usageDetail}>Записанный остаток: {metricValue(row.key, row.remaining)}</span> : null}
              </div>
            </td>
            <td>{limit === undefined ? 'Лимит не записан' : metricValue(row.key, limit)}</td>
          </tr>;
        }
        return <tr key={row.key}><td>{row.label}</td><td>{metricValue(row.key, row.used)}</td><td>{metricValue(row.key, row.limit)}</td><td>{metricValue(row.key, row.remaining)}</td><td><Badge size="small" tone={tone}>{status}</Badge></td></tr>;
      })}
    </InspectorTable>
  </InspectorSection>;
}

export function LimitsViewer({ limits }: { limits?: TraceLimitsView }) {
  if (!limits?.rows.length) return <InspectorEmptyState message="Локальные ограничения для этого исполнителя не записаны в журнал." />;
  return <InspectorStack><LimitsTable view={limits} title="Ограничения исполнителя" /></InspectorStack>;
}

export function AgentLimitsViewer({ limits, statistics }: { limits?: TraceLimitsView; statistics: TraceExecutorStatistic[] }) {
  const rows = new Map((limits?.rows ?? []).map((row) => [row.key, row]));
  for (const statistic of statistics.filter((item) => item.key === 'tokens_in' || item.key === 'tokens_out' || item.key === 'tokens_total')) {
    const existing = rows.get(statistic.key);
    const limit = existing?.limit ?? statistic.limit?.limit;
    const remaining = limit === undefined ? undefined : Math.max(0, limit - statistic.value);
    const status: LimitRow['status'] = limit === undefined ? 'neutral'
      : statistic.value > limit || remaining === 0 ? 'exceeded'
        : statistic.value / limit >= 0.8 ? 'warning' : 'ok';
    rows.set(statistic.key, {
      key: statistic.key,
      label: statistic.label,
      used: statistic.value,
      limit,
      remaining,
      status,
    });
  }
  const tokenOrder = ['tokens_in', 'tokens_out', 'tokens_total'];
  const view: TraceLimitsView = { rows: [...rows.values()].sort((left, right) => {
    const leftTokenIndex = tokenOrder.indexOf(left.key);
    const rightTokenIndex = tokenOrder.indexOf(right.key);
    if (leftTokenIndex >= 0 || rightTokenIndex >= 0) {
      return (leftTokenIndex < 0 ? tokenOrder.length : leftTokenIndex)
        - (rightTokenIndex < 0 ? tokenOrder.length : rightTokenIndex);
    }
    return left.label.localeCompare(right.label, 'ru');
  }) };
  if (!view.rows.length) return <InspectorEmptyState message="Лимиты и фактический расход для этого запуска не записаны." />;
  return <InspectorStack><LimitsTable view={view} title="Лимиты и расход" agentCompact /></InspectorStack>;
}

export function RbacViewer({ access }: { access?: TraceAccessView }) {
  if (!access) return <InspectorEmptyState message="RBAC-снимок для этого запуска не записан." />;
  if (!access.rows.length && access.defaultCollectionAllow === undefined) return <InspectorEmptyState message="RBAC-снимок не содержит решений доступа." />;
  return <InspectorStack>
    {access.defaultCollectionAllow !== undefined ? <InspectorNotice tone={access.defaultCollectionAllow ? 'info' : 'warn'} message={`Коллекции без явного правила: ${access.defaultCollectionAllow ? 'разрешены' : 'запрещены'}.`} /> : null}
    {access.rows.length ? <InspectorTable compact columnWidths={['35%', '26%', '39%']} headers={['Сущность', 'Доступ', 'Причина']}>
      {access.rows.map((row) => <tr key={`${row.kind}:${row.name}:${row.reason}`}><td>{row.kind}: <code>{row.name}</code></td><td><Badge size="small" tone={row.allowed ? 'success' : 'danger'}>{row.allowed ? 'Разрешено' : 'Запрещено'}</Badge></td><td>{row.reason}</td></tr>)}
    </InspectorTable> : null}
  </InspectorStack>;
}

const statusPresentation = (item: TraceAccessItem): { label: string; tone: 'neutral' | 'success' | 'warn' | 'danger'; detail?: string } => {
  if (item.status === 'available') return { label: 'Доступен', tone: 'success' };
  if (item.status === 'unknown') return { label: 'Не проверен', tone: 'neutral' };
  if (item.status === 'limited') return {
    label: item.reasonCode === 'missing_credentials' ? 'Ограничен · Preflight' : 'Ограничен',
    tone: 'warn', detail: item.reason,
  };
  if (item.reasonCode === 'blocked_by_rbac') return { label: 'Запрещён · RBAC', tone: 'danger', detail: item.reason };
  if (item.reasonCode === 'outside_agent_access') return { label: 'Недоступен · настройки агента', tone: 'danger', detail: item.reason };
  return { label: 'Недоступен · Preflight', tone: 'danger', detail: item.reason };
};

interface AccessRow {
  item: TraceAccessItem;
  source?: string;
  description?: string;
}

function AccessTable({ rows, title, agentCompact = false }: { rows: AccessRow[]; title: string; agentCompact?: boolean }) {
  if (!rows.length) return null;
  return <InspectorSection title={title}>
    <InspectorTable compact columnWidths={agentCompact ? undefined : ['28%', '20%', '24%', '28%']} headers={agentCompact ? ['Название', 'Доступ'] : ['Название', 'Источник', 'Статус', 'Описание']}>
      {rows.map(({ item, source, description }) => {
        const status = statusPresentation(item);
        if (agentCompact) return <tr key={`${item.kind}:${item.key}`}>
          <td className={styles.nameCell}>
            <div>{item.label}</div>
            {item.kind === 'tool' && source ? <div className={styles.sourceBadge}><SourceBadge source={source} /></div> : null}
            {description || item.description ? <details className={styles.descriptionDisclosure}>
              <summary>Описание</summary><span>{description || item.description}</span>
            </details> : null}
          </td>
          <td><span className={styles.statusCell}><Badge size="small" tone={status.tone}>{status.label}</Badge>{status.detail ? <details className={styles.descriptionDisclosure}><summary>Причина</summary><span>{status.detail}</span></details> : null}</span></td>
        </tr>;
        return <tr key={`${item.kind}:${item.key}`}>
          <td className={styles.nameCell}>{item.label}</td>
          <td>{item.kind === 'tool' && source ? <SourceBadge source={source} /> : '—'}</td>
          <td><span className={styles.statusCell}><Badge size="small" tone={status.tone}>{status.label}</Badge>{status.detail ? <span className={styles.secondary}>{status.detail}</span> : null}</span></td>
          <td>{description || item.description || '—'}</td>
        </tr>;
      })}
    </InspectorTable>
  </InspectorSection>;
}

const sourceTone = (source: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' => {
  const normalized = source.trim().toLocaleLowerCase('ru-RU');
  if (normalized === 'система') return 'neutral';
  if (normalized.startsWith('dcbox')) return 'info';
  if (normalized.startsWith('jira')) return 'success';
  if (normalized.startsWith('confluence')) return 'warn';
  if (normalized.startsWith('netbox')) return 'danger';
  return 'neutral';
};

function SourceBadge({ source }: { source: string }) {
  const tone = sourceTone(source);
  return <Badge size="small" tone={tone} data-source-tone={tone} aria-label={`Источник: ${source}`}>{source}</Badge>;
}

const toolsFromSources = (sources: TraceAccessItem[]): AccessRow[] => sources.flatMap((source) =>
  source.children.filter((item) => item.kind === 'tool').map((item) => ({
    item,
    source: item.sourceLabel || source.label,
    description: item.description,
  })),
);

export function AccessSnapshotViewer({ snapshot }: { snapshot?: TraceAccessSnapshot }) {
  if (!snapshot) return <InspectorEmptyState message="Доступ для этого запуска не записан." />;
  const agents = snapshot.items.filter((item) => item.kind === 'agent').map((item) => ({
    item, description: item.description || snapshot.agentDescription,
  }));
  const sources = snapshot.items.filter((item) => item.kind === 'source').map((item) => ({ item, description: item.description }));
  const topLevelTools = snapshot.items.filter((item) => item.kind === 'tool');
  const directToolFallback = snapshot.entityType === 'planner' || snapshot.entityType === 'agent' ? 'Система' : undefined;
  const systemTools = topLevelTools.map((item) => ({
    item,
    source: item.sourceLabel || directToolFallback,
    description: item.description,
  }));
  const sourceTools = toolsFromSources(snapshot.items.filter((item) => item.kind === 'source'));

  if (snapshot.entityType === 'planner') return <InspectorStack>
    <AccessTable title="Агенты" rows={agents} />
    <AccessTable title="Инструменты планера" rows={systemTools} />
    {!agents.length && !systemTools.length ? <InspectorEmptyState message="Настроенные агенты и инструменты не записаны." /> : null}
  </InspectorStack>;

  if (snapshot.entityType === 'agent') return <InspectorStack>
    <AccessTable title="Источники данных" rows={sources} agentCompact />
    <AccessTable title="Инструменты" rows={[...sourceTools, ...systemTools]} agentCompact />
    {!sources.length && !sourceTools.length && !systemTools.length ? <InspectorEmptyState message="Настроенные источники и инструменты не записаны." /> : null}
  </InspectorStack>;

  return <InspectorStack>
    <AccessTable title="Инструменты проверки" rows={systemTools} />
    {!systemTools.length ? <InspectorEmptyState message="Инструменты проверки не записаны." /> : null}
  </InspectorStack>;
}
