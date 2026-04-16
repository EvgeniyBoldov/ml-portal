/**
 * Unified status configuration for all entity types.
 *
 * Single source of truth for labels and Badge tones.
 * Import `getStatusProps` instead of defining local STATUS_LABELS / STATUS_TONES.
 */

export type BadgeTone = 'success' | 'warn' | 'danger' | 'neutral' | 'info' | 'warning';

export interface StatusProps {
  label: string;
  tone: BadgeTone;
}

/* ─── Version statuses (prompts, policies, tools, limits, baselines) ─── */
const VERSION_STATUSES: Record<string, StatusProps> = {
  draft:    { label: 'Черновик',  tone: 'warn' },
  active:   { label: 'Активна',  tone: 'success' },
  archived: { label: 'Архив',    tone: 'neutral' },
  inactive: { label: 'Неактивна', tone: 'neutral' },
};

/* ─── Model statuses ─── */
const MODEL_STATUSES: Record<string, StatusProps> = {
  available:   { label: 'Доступна',     tone: 'success' },
  deprecated:  { label: 'Устарела',     tone: 'warn' },
  unavailable: { label: 'Недоступна',   tone: 'danger' },
  maintenance: { label: 'Обслуживание', tone: 'danger' },
};

/* ─── Agent run statuses ─── */
const RUN_STATUSES: Record<string, StatusProps> = {
  pending:   { label: 'Ожидает',     tone: 'neutral' },
  running:   { label: 'Выполняется', tone: 'info' },
  completed: { label: 'Завершён',    tone: 'success' },
  failed:    { label: 'Ошибка',      tone: 'danger' },
  cancelled: { label: 'Отменён',     tone: 'warn' },
};

/* ─── Instance health statuses ─── */
const HEALTH_STATUSES: Record<string, StatusProps> = {
  healthy:   { label: 'Здоров',    tone: 'success' },
  unhealthy: { label: 'Нездоров',  tone: 'danger' },
  unknown:   { label: 'Неизвестно', tone: 'warn' },
};

/* ─── Credential statuses ─── */
const CREDENTIAL_STATUSES: Record<string, StatusProps> = {
  active:   { label: 'Активен',   tone: 'success' },
  inactive: { label: 'Неактивен', tone: 'neutral' },
  expired:  { label: 'Истёк',     tone: 'danger' },
};

/* ─── Model type labels ─── */
export const MODEL_TYPE_LABELS: Record<string, string> = {
  llm_chat:  'LLM',
  embedding: 'Embedding',
  reranker:  'Reranker',
};

/* ─── Registry ─── */
export type StatusDomain =
  | 'version'
  | 'model'
  | 'run'
  | 'health'
  | 'credential';

const STATUS_REGISTRY: Record<StatusDomain, Record<string, StatusProps>> = {
  version:    VERSION_STATUSES,
  model:      MODEL_STATUSES,
  run:        RUN_STATUSES,
  health:     HEALTH_STATUSES,
  credential: CREDENTIAL_STATUSES,
};

const FALLBACK: StatusProps = { label: '—', tone: 'neutral' };

/**
 * Get label + tone for a given status value within a domain.
 *
 * @example
 * const { label, tone } = getStatusProps('version', 'draft');
 * // → { label: 'Черновик', tone: 'warn' }
 */
export function getStatusProps(domain: StatusDomain, status: string): StatusProps {
  return STATUS_REGISTRY[domain]?.[status] ?? { label: status, tone: 'neutral' };
}

/**
 * Get just the label.
 */
export function getStatusLabel(domain: StatusDomain, status: string): string {
  return (STATUS_REGISTRY[domain]?.[status] ?? FALLBACK).label;
}

/**
 * Get just the tone.
 */
export function getStatusTone(domain: StatusDomain, status: string): BadgeTone {
  return (STATUS_REGISTRY[domain]?.[status] ?? FALLBACK).tone;
}
