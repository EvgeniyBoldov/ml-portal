import React from 'react';
import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { BudgetMetric, EntityLimits, EntityUsed, ErrorData, TraceContextSnapshot, TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { getTraceEntityKindLabel } from '@/domains/runtimeTrace/tracePresentation';
import { BudgetTable, SpendSummary } from '@/domains/runtimeTrace/budget';
import type { RunStep } from '../../hooks/useSandboxRun';

export function formatDuration(ms?: number): string {
  if (ms === undefined) return '—';
  return `${(ms / 1000).toFixed(1).replace('.', ',')} s`;
}

export function statusLabel(status: TraceEntity['status']): string {
  if (status === 'ok') return 'Успешно';
  if (status === 'warn') return 'Предупреждение';
  if (status === 'error') return 'Ошибка';
  if (status === 'pending') return 'В процессе';
  return 'Инфо';
}

export function statusTone(status: TraceEntity['status']): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (status === 'error') return 'danger';
  if (status === 'warn') return 'warn';
  if (status === 'ok') return 'success';
  if (status === 'pending') return 'info';
  return 'neutral';
}

export function InfoTab({
  entity,
  steps,
  showTitle = true,
  showId = false,
}: {
  entity: TraceEntity;
  steps: RunStep[];
  showTitle?: boolean;
  showId?: boolean;
}) {
  const stepCount = steps.length;

  return (
    <InspectorFieldGroup>
      <SnapshotBadgeField label="Тип" tone="neutral" text={getTraceEntityKindLabel(entity)} />
      <SnapshotBadgeField label="Статус" tone={statusTone(entity.status)} text={statusLabel(entity.status)} />
      <SnapshotValueField label="Длительность" value={formatDuration(entity.durationMs)} />
      <SnapshotValueField label="Шагов" value={stepCount > 0 ? String(stepCount) : '—'} />
      {showId ? <SnapshotCodeField label="ID" value={entity.id} truncate /> : null}
      {showTitle && entity.title ? <SnapshotTextField label="Заголовок" text={entity.title} /> : null}
    </InspectorFieldGroup>
  );
}

export function InfoTabContent({
  entity,
  steps,
  showTitle = true,
  showId = false,
}: {
  entity: TraceEntity;
  steps: RunStep[];
  showTitle?: boolean;
  showId?: boolean;
}) {
  return <InfoTab entity={entity} steps={steps} showTitle={showTitle} showId={showId} />;
}

export function SnapshotValueField({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  const normalized = value === null || value === undefined || value === '' ? '—' : String(value);
  return <InspectorFieldRow label={label}>{normalized}</InspectorFieldRow>;
}

export function SnapshotCodeField({
  label,
  value,
  truncate = false,
}: {
  label: string;
  value: string | number | null | undefined;
  truncate?: boolean;
}) {
  const normalized = value === null || value === undefined || value === '' ? '—' : String(value);
  const display = truncate && normalized !== '—' ? `${normalized.slice(0, 16)}...` : normalized;
  return (
    <InspectorFieldRow label={label}>
      <code>{display}</code>
    </InspectorFieldRow>
  );
}

export function SnapshotBadgeField({
  label,
  text,
  tone,
}: {
  label: string;
  text: string;
  tone: 'neutral' | 'success' | 'warn' | 'danger' | 'info';
}) {
  return (
    <InspectorFieldRow label={label}>
      <Badge tone={tone} size="sm">{text}</Badge>
    </InspectorFieldRow>
  );
}

export function SnapshotTextField({
  label,
  text,
}: {
  label: string;
  text: string | null | undefined;
}) {
  const normalized = typeof text === 'string' && text.trim().length > 0 ? text : '—';
  return (
    <InspectorFieldRow label={label}>
      <InspectorTextBlock text={normalized} />
    </InspectorFieldRow>
  );
}

export function SnapshotJsonField({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  return (
    <InspectorFieldRow label={label}>
      <InspectorJsonBlock value={value ?? '—'} />
    </InspectorFieldRow>
  );
}

export function getEntityErrors(entity: TraceEntity): ErrorData[] {
  const data = entity.data as unknown as Record<string, unknown> & { errors?: unknown };
  if (!Array.isArray(data.errors)) return [];
  return data.errors.filter((item): item is ErrorData => !!item && typeof item === 'object' && (item as ErrorData).kind === 'error');
}

export function EntityErrorsTab({ entity }: { entity: TraceEntity }) {
  const errors = getEntityErrors(entity);
  if (errors.length === 0) {
    return (
      <InspectorFieldGroup>
        <SnapshotValueField label="Ошибки" value="—" />
      </InspectorFieldGroup>
    );
  }
  return (
    <InspectorFieldGroup>
      <SnapshotValueField label="Ошибок" value={String(errors.length)} />
      {errors.map((error, index) => (
        <InspectorFieldGroup key={`${entity.id}:error:${index}`}>
          <SnapshotValueField label="Источник" value={error.sourceLabel ?? '—'} />
          <SnapshotValueField label="Код" value={error.code ?? '—'} />
          <SnapshotTextField label="Сообщение" text={error.userMessage ?? '—'} />
          <SnapshotTextField label="Техническая ошибка" text={error.operatorMessage ?? '—'} />
          <SnapshotValueField label="Тип исключения" value={error.debug?.exceptionType ?? '—'} />
          <SnapshotTextField label="Traceback" text={error.debug?.stack ?? '—'} />
          <SnapshotJsonField label="Контекст" value={error.debug?.context ?? null} />
        </InspectorFieldGroup>
      ))}
    </InspectorFieldGroup>
  );
}

function toRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function num(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function mergeNumericEntityUsed(target: EntityUsed, source: EntityUsed): EntityUsed {
  const out: EntityUsed = { ...target };
  for (const [key, value] of Object.entries(source) as Array<[keyof EntityUsed, number | undefined]>) {
    if (typeof value !== 'number') continue;
    out[key] = Number(out[key] ?? 0) + value;
  }
  return out;
}

function mergeNumericEntityLimits(target: EntityLimits, source: EntityLimits): EntityLimits {
  const out: EntityLimits = { ...target };
  for (const [key, value] of Object.entries(source) as Array<[keyof EntityLimits, number | undefined]>) {
    if (typeof value !== 'number') continue;
    out[key] = value;
  }
  return out;
}

function collectBudgetFromSteps(steps: RunStep[]): { used: EntityUsed; limits: EntityLimits | null } | null {
  let used: EntityUsed = {};
  let limits: EntityLimits = {};
  let hasData = false;

  for (const step of steps) {
    const budget = extractBudgetFromStep(step);
    if (!budget) continue;
    hasData = true;
    used = mergeNumericEntityUsed(used, budget.used);
    if (budget.limits) limits = mergeNumericEntityLimits(limits, budget.limits);
  }

  if (!hasData) return null;
  return {
    used,
    limits: Object.keys(limits).length > 0 ? limits : null,
  };
}

const METRICS: BudgetMetric[] = [
  'planner_steps',
  'agent_steps',
  'tool_calls',
  'tokens_in',
  'tokens_out',
  'tokens_total',
  'retries',
  'wall_time_ms',
];

function extractBudgetFromStep(step: RunStep): { used: EntityUsed; limits: EntityLimits | null } | undefined {
  const d = step.data as Record<string, unknown>;
  const own = toRecord(d.own);
  const limits = toRecord(d.limits);
  if (!own && !limits) return undefined;

  const used: EntityUsed = {};
  const entityLimits: EntityLimits = {};

  for (const metric of METRICS) {
    const usedVal = num(own?.[metric]);
    if (usedVal !== undefined) used[metric] = usedVal;
    const limitVal = num(limits?.[metric]);
    if (limitVal !== undefined) entityLimits[metric] = limitVal;
  }

  return {
    used,
    limits: Object.keys(entityLimits).length > 0 ? entityLimits : null,
  };
}

function budgetTitleForEntity(entity: TraceEntity): string {
  if (getTraceEntityKindLabel(entity) === 'Оркестратор' && entity.kind === 'agent') {
    return 'Бюджет оркестратора';
  }
  const kind = entity.kind;
  if (kind === 'phase') return 'Расход фазы';
  if (kind === 'agent') return 'Бюджет агента';
  if (kind === 'planner' || kind === 'decision' || kind === 'orchestrator') return 'Бюджет оркестратора';
  if (kind === 'tool') return 'Расход инструмента';
  if (kind === 'run') return 'Бюджет запуска';
  return 'Использование бюджета';
}

export function BudgetsTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const fromSteps = collectBudgetFromSteps(steps);

  const used = (entity.kind === 'run' || entity.kind === 'orchestrator' || entity.kind === 'agent' || entity.kind === 'phase')
    ? (entity.budget?.aggregated ?? fromSteps?.used ?? {})
    : (entity.budget?.own ?? fromSteps?.used ?? {});
  const limits = entity.kind === 'phase' ? null : (entity.budget?.limits ?? fromSteps?.limits);

  if (limits && Object.keys(limits).length > 0) {
    return (
      <BudgetTable
        title={budgetTitleForEntity(entity)}
        used={used}
        limits={limits}
      />
    );
  }

  return <SpendSummary used={used} />;
}

export function SpendTab({ entity }: { entity: TraceEntity }) {
  return <SpendSummary used={entity.budget?.aggregated ?? {}} />;
}

export function getStepPromptSnapshot(step: RunStep): string | undefined {
  const data = (step.data ?? {}) as Record<string, unknown>;
  const nestedSnapshot = data.context_snapshot && typeof data.context_snapshot === 'object'
    ? (data.context_snapshot as Record<string, unknown>)
    : undefined;

  const promptCandidates: Array<unknown> = [
    data.prompt,
    data.system_prompt,
    data.compiled_prompt,
    nestedSnapshot?.prompt,
    nestedSnapshot?.system_prompt,
    nestedSnapshot?.compiled_prompt,
    nestedSnapshot?.systemPrompt,
  ];

  for (const candidate of promptCandidates) {
    if (typeof candidate === 'string' && candidate.trim().length > 0) return candidate;
    if (!candidate || typeof candidate !== 'object') continue;
    const record = candidate as Record<string, unknown>;
    if (typeof record.systemPrompt === 'string' && record.systemPrompt.trim().length > 0) return record.systemPrompt;
    if (typeof record.system_prompt === 'string' && record.system_prompt.trim().length > 0) return record.system_prompt;
    if (typeof record.compiled_prompt === 'string' && record.compiled_prompt.trim().length > 0) return record.compiled_prompt;
    if (Array.isArray(record.messages)) {
      const systemMsg = record.messages.find((msg) => typeof msg === 'object' && msg !== null && String((msg as Record<string, unknown>).role ?? '') === 'system');
      const content = systemMsg && typeof systemMsg === 'object'
        ? (systemMsg as Record<string, unknown>).content
        : undefined;
      if (typeof content === 'string' && content.trim().length > 0) return content;
    }
  }

  return undefined;
}

export function getStepsPromptSnapshot(steps: RunStep[]): string | undefined {
  for (const step of steps) {
    const prompt = getStepPromptSnapshot(step);
    if (prompt) return prompt;
  }
  return undefined;
}

export function getEntityPromptSnapshot(entity: TraceEntity): string | undefined {
  const data = entity.data as unknown as Record<string, unknown> | undefined;
  if (!data) return undefined;

  const entitySnapshot = getEntityContextSnapshot(entity);
  if (typeof entitySnapshot?.system_prompt === 'string' && entitySnapshot.system_prompt.trim().length > 0) {
    return entitySnapshot.system_prompt;
  }

  const directCandidates = [
    data.prompt,
    data.system_prompt,
    data.compiled_prompt,
    data.systemPrompt,
  ];

  for (const candidate of directCandidates) {
    if (typeof candidate === 'string' && candidate.trim().length > 0) return candidate;
  }

  if (data.prompt && typeof data.prompt === 'object') {
    const promptObj = data.prompt as Record<string, unknown>;
    if (typeof promptObj.systemPrompt === 'string' && promptObj.systemPrompt.trim().length > 0) {
      return promptObj.systemPrompt;
    }
    if (typeof promptObj.system_prompt === 'string' && promptObj.system_prompt.trim().length > 0) {
      return promptObj.system_prompt;
    }
  }

  const contextSnapshot = getEntityContextSnapshot(entity) as Record<string, unknown> | undefined;
  if (contextSnapshot) {
    const snapshotCandidates = [
      contextSnapshot.prompt,
      contextSnapshot.system_prompt,
      contextSnapshot.compiled_prompt,
      contextSnapshot.systemPrompt,
    ];

    for (const candidate of snapshotCandidates) {
      if (typeof candidate === 'string' && candidate.trim().length > 0) return candidate;
    }

    // Check nested prompt in context_snapshot
    if (contextSnapshot.prompt && typeof contextSnapshot.prompt === 'object') {
      const promptObj = contextSnapshot.prompt as Record<string, unknown>;
      if (typeof promptObj.systemPrompt === 'string' && promptObj.systemPrompt.trim().length > 0) {
        return promptObj.systemPrompt;
      }
      if (typeof promptObj.system_prompt === 'string' && promptObj.system_prompt.trim().length > 0) {
        return promptObj.system_prompt;
      }
    }

    // Check messages array for system message
    if (Array.isArray(contextSnapshot.messages)) {
      const systemMsg = contextSnapshot.messages.find(
        (msg) => typeof msg === 'object' && msg !== null && String((msg as Record<string, unknown>).role ?? '') === 'system'
      );
      if (systemMsg && typeof systemMsg === 'object') {
        const content = (systemMsg as Record<string, unknown>).content;
        if (typeof content === 'string' && content.trim().length > 0) return content;
      }
    }
  }

  return undefined;
}

export function getEntityContextSnapshot(entity: TraceEntity): TraceContextSnapshot | undefined {
  const data = entity.data as unknown as Record<string, unknown> | undefined;
  if (!data) return undefined;
  const snapshot = data.contextSnapshot ?? data.context_snapshot;
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return undefined;
  return snapshot as TraceContextSnapshot;
}

export function getEntityInputsSnapshot(entity: TraceEntity): TraceContextSnapshot['inputs'] | undefined {
  return getEntityContextSnapshot(entity)?.inputs;
}

export function getEntityMetaSnapshot(entity: TraceEntity): TraceContextSnapshot['meta'] | undefined {
  return getEntityContextSnapshot(entity)?.meta;
}

export function getEntityRbacSnapshot(entity: TraceEntity): TraceContextSnapshot['rbac'] | undefined {
  return getEntityContextSnapshot(entity)?.rbac;
}

export function getEntityLimitsSnapshot(entity: TraceEntity): TraceContextSnapshot['limits'] | undefined {
  return getEntityContextSnapshot(entity)?.limits;
}

export function getPromptSnapshot(entity: TraceEntity, steps: RunStep[]): string | undefined {
  // Priority: entity data > steps data
  return getEntityPromptSnapshot(entity) ?? getStepsPromptSnapshot(steps);
}

export function RawTab({ value, entity, steps }: { value: unknown; entity?: TraceEntity; steps?: RunStep[] }) {
  const hiddenContractKeys = new Set([
    'response_contract',
    'input_contract',
    'contract',
    'contracts',
  ]);

  const sanitizeForInspector = (input: unknown): unknown => {
    if (Array.isArray(input)) {
      return input.map(sanitizeForInspector);
    }
    if (!input || typeof input !== 'object') {
      return input;
    }
    const source = input as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [key, raw] of Object.entries(source)) {
      if (hiddenContractKeys.has(key)) continue;
      out[key] = sanitizeForInspector(raw);
    }
    return out;
  };

  const safeValue = sanitizeForInspector(value);

  if (!entity || !steps || steps.length === 0) {
    return (
      <InspectorFieldGroup>
        <InspectorJsonBlock value={safeValue} />
      </InspectorFieldGroup>
    );
  }

  return (
    <InspectorFieldGroup>
      {steps.map((step, index) => (
        <InspectorJsonBlock
          key={step.id}
          value={{
            index,
            id: step.id,
            type: step.type,
            timestamp: step.timestamp,
            data: sanitizeForInspector(step.data),
          }}
        />
      ))}
    </InspectorFieldGroup>
  );
}
