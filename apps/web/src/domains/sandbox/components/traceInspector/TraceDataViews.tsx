import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';
import { HumanPlanView } from './PlanView';
import type { PlanViewModel } from '../../planInspection';
import styles from './TraceDataViews.module.css';

type RecordValue = Record<string, unknown>;
type LimitRow = { key: string; label: string; used?: number; limit?: number; remaining?: number };
type AccessRow = { kind: string; name: string; allowed: boolean; reason: string };

const record = (value: unknown): RecordValue => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {}
);
const number = (value: unknown): number | undefined => typeof value === 'number' && Number.isFinite(value) ? value : undefined;
const metricLabels: Record<string, string> = {
  agent_steps: 'Шаги агента', planner_steps: 'Шаги планера', plan_revisions: 'Ревизии плана',
  task_attempts: 'Попытки задач', agent_runs: 'Запуски агентов', llm_calls: 'Вызовы LLM',
  tool_calls: 'Вызовы инструментов', tokens_in: 'Входные токены', tokens_out: 'Выходные токены',
  tokens_total: 'Всего токенов', retries: 'Повторы', wall_time_ms: 'Время выполнения',
};
const labelForMetric = (key: string): string => metricLabels[key] ?? key.replace(/_/g, ' ');
const formatValue = (key: string, value: number | undefined): string => {
  if (value === undefined) return '—';
  if (key === 'wall_time_ms') return value >= 1000 ? `${(value / 1000).toFixed(value % 1000 ? 1 : 0)} с` : `${value} мс`;
  return new Intl.NumberFormat('ru-RU').format(value);
};

export function normalizeLimits(snapshot: unknown): LimitRow[] {
  const value = record(snapshot);
  const nested = record(value.snapshot);
  const own = record(value.own);
  const limits = record(value.limits ?? value.runtime_limits);
  const keys = new Set([...Object.keys(nested), ...Object.keys(own), ...Object.keys(limits)]);
  return [...keys].map((key) => {
    const metric = record(nested[key]);
    const used = number(metric.used) ?? number(own[key]);
    const limit = number(metric.limit) ?? number(limits[key]);
    const remaining = number(metric.remaining) ?? (limit !== undefined && used !== undefined ? Math.max(0, limit - used) : undefined);
    return { key, label: labelForMetric(key), used, limit, remaining };
  }).filter((row) => row.used !== undefined || row.limit !== undefined).sort((left, right) => left.label.localeCompare(right.label, 'ru'));
}

function limitTone(row: LimitRow): 'neutral' | 'success' | 'warn' | 'danger' {
  if (row.limit === undefined) return 'neutral';
  if ((row.used ?? 0) > row.limit || row.remaining === 0) return 'danger';
  if ((row.used ?? 0) / row.limit >= 0.8) return 'warn';
  return 'success';
}

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
        return <tr key={row.key}><td>{row.label}</td><td>{formatValue(row.key, row.used)}</td><td>{formatValue(row.key, row.limit)}</td><td>{formatValue(row.key, row.remaining)}</td><td><Badge size="small" tone={tone}>{status}</Badge></td></tr>;
      })}</tbody>
    </table></div>
  </section>;
}

export function accessRows(rbac: RecordValue): AccessRow[] {
  const rows: AccessRow[] = [];
  const add = (kind: string, values: unknown, allowed: boolean, reason: string) => {
    for (const value of Array.isArray(values) ? values : []) {
      if (typeof value === 'string' && value) rows.push({ kind, name: value, allowed, reason });
    }
  };
  add('Агент', rbac.allowed, true, 'Разрешён эффективной политикой');
  add('Агент', rbac.denied_by_rbac, false, 'Запрещён RBAC');
  const collections = record(rbac.collection_filter);
  add('Коллекция', collections.allowed, true, 'Доступна выбранному агенту');
  add('Коллекция', collections.denied_by_rbac, false, 'Запрещена RBAC');
  add('Коллекция', collections.denied_by_capability, false, 'Не входит в capability агента');
  return rows.sort((left, right) => left.kind.localeCompare(right.kind, 'ru') || left.name.localeCompare(right.name, 'ru'));
}

export function PlanView({ plan }: { plan?: PlanViewModel }) {
  return <HumanPlanView plan={plan} />;
}

export function LimitsView({ executorSnapshot, runSnapshot }: { executorSnapshot: unknown; runSnapshot: unknown }) {
  const ownRows = normalizeLimits(executorSnapshot);
  const runRows = normalizeLimits(runSnapshot);
  if (!ownRows.length && !runRows.length) return <InspectorNotice tone="neutral" message="Лимиты для этого запуска не записаны в журнал." />;
  return <div className={styles.stack}>
    {ownRows.length ? <LimitsTable snapshot={executorSnapshot} title="Текущий запуск" /> : null}
    {runRows.length ? <LimitsTable snapshot={runSnapshot} title="Общий лимит run" /> : null}
  </div>;
}

export function RbacView({ snapshot }: { snapshot: unknown }) {
  const value = record(snapshot);
  const rbac = record(value.rbac ?? value);
  const rows = accessRows(rbac);
  const defaultAllow = typeof rbac.default_collection_allow === 'boolean'
    ? rbac.default_collection_allow
    : typeof record(rbac.collection_filter).default_collection_allow === 'boolean'
      ? record(rbac.collection_filter).default_collection_allow as boolean
      : undefined;
  if (!rows.length) return <InspectorNotice tone="neutral" message="RBAC-снимок для этого запуска не записан." />;
  return <div className={styles.stack}>
    {defaultAllow !== undefined ? <InspectorNotice tone={defaultAllow ? 'info' : 'warn'} message={`Коллекции без явного правила: ${defaultAllow ? 'разрешены' : 'запрещены'}. Операции наследуют доступ от коллекций.`} /> : null}
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th>Тип</th><th>Сущность</th><th>Доступ</th><th>Причина</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={`${row.kind}:${row.name}:${row.reason}`}><td>{row.kind}</td><td><code>{row.name}</code></td><td><Badge size="small" tone={row.allowed ? 'success' : 'danger'}>{row.allowed ? 'Разрешено' : 'Запрещено'}</Badge></td><td>{row.reason}</td></tr>)}</tbody>
    </table></div>
  </div>;
}

const configLabels: Record<string, string> = {
  model: 'Модель', temperature: 'Temperature', max_tokens: 'Макс. токенов',
  streaming_enabled: 'Streaming', citations_required: 'Требуются цитаты',
  allow_parallel_tool_calls: 'Параллельные вызовы инструментов',
};

export function ExecutorSnapshotView({ snapshot }: { snapshot: unknown }) {
  const value = record(snapshot);
  const config = record(value.config_snapshot ?? value);
  const meta = record(config.meta);
  const limits = record(config.limits);
  const prompt = typeof config.system_prompt === 'string' ? config.system_prompt : '';
  const promptHash = typeof config.system_prompt_hash === 'string' ? config.system_prompt_hash : '';
  const settings = Object.entries(meta)
    .filter(([key, value]) => key in configLabels && value !== null && value !== undefined)
    .map(([key, value]) => ({ label: configLabels[key], value }));
  const limitSettings = Object.entries(limits).map(([key, value]) => ({ label: labelForMetric(key), value }));
  if (!settings.length && !limitSettings.length && !prompt && !promptHash) {
    return <InspectorNotice tone="neutral" message="Снимок настроек запуска не записан в журнал." />;
  }
  return <div className={styles.stack}>
    {(settings.length || limitSettings.length) ? <InspectorFieldGroup>
      {settings.map((item) => <InspectorFieldRow key={item.label} label={item.label}><InspectorScalar value={item.value as string | number | boolean | null | undefined} /></InspectorFieldRow>)}
      {limitSettings.map((item) => <InspectorFieldRow key={item.label} label={item.label}><InspectorScalar value={item.value as string | number | boolean | null | undefined} /></InspectorFieldRow>)}
    </InspectorFieldGroup> : null}
    {prompt ? <section className={styles.section}><h4>Системный промпт</h4><InspectorTextBlock text={prompt} /></section> : null}
    {!prompt && promptHash ? <InspectorNotice tone="neutral" title="Промпт скрыт" message="Для этого запуска сохранён только хеш системного промпта согласно уровню логирования." code={promptHash} /> : null}
  </div>;
}

export function TextValue({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || ['string', 'number', 'boolean'].includes(typeof value)) {
    return <InspectorFieldRow label={label}><InspectorScalar value={value as string | number | boolean | null | undefined} /></InspectorFieldRow>;
  }
  return <InspectorFieldRow label={label}><InspectorJsonBlock value={value} /></InspectorFieldRow>;
}
