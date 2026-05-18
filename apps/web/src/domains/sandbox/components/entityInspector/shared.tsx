import React from 'react';
import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock } from '@/shared/ui/Inspector';
import type { BudgetMetric, EntityLimits, EntityUsed, TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { BudgetTable, SpendSummary } from '@/domains/runtimeTrace/budget';
import type { RunStep } from '../../hooks/useSandboxRun';

export function formatDuration(ms?: number): string {
  if (ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function statusTone(status: TraceEntity['status']): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (status === 'error') return 'danger';
  if (status === 'warn') return 'warn';
  if (status === 'ok') return 'success';
  if (status === 'pending') return 'info';
  return 'neutral';
}

export function kindLabel(kind: string): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

export function InfoTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const stepCount = steps.filter((s) => entity.sourceEventIds?.includes(s.id) || entity.sourceEventIds?.length === 0).length;

  return (
    <InspectorFieldGroup>
      <InspectorFieldRow label="Type"><Badge tone="neutral" size="sm">{kindLabel(entity.kind)}</Badge></InspectorFieldRow>
      <InspectorFieldRow label="Status"><Badge tone={statusTone(entity.status)} size="sm">{entity.status}</Badge></InspectorFieldRow>
      <InspectorFieldRow label="Duration">{formatDuration(entity.durationMs)}</InspectorFieldRow>
      <InspectorFieldRow label="Steps">{stepCount > 0 ? stepCount : '—'}</InspectorFieldRow>
      <InspectorFieldRow label="ID"><code>{entity.id.slice(0, 16)}...</code></InspectorFieldRow>
      {entity.title ? <InspectorFieldRow label="Title">{entity.title}</InspectorFieldRow> : null}
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

function budgetTitleForKind(kind: TraceEntity['kind']): string {
  if (kind === 'agent') return 'Бюджет агента';
  if (kind === 'planner' || kind === 'decision' || kind === 'orchestrator') return 'Бюджет оркестратора';
  if (kind === 'tool') return 'Расход инструмента';
  if (kind === 'run') return 'Бюджет запуска';
  return 'Использование бюджета';
}

export function BudgetsTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const fromStep = steps
    .filter((step) => entity.sourceEventIds.includes(step.id))
    .map(extractBudgetFromStep)
    .find(Boolean);

  const used = entity.kind === 'run'
    ? (entity.budget?.aggregated ?? fromStep?.used ?? {})
    : (entity.budget?.own ?? fromStep?.used ?? {});
  const limits = entity.budget?.limits ?? fromStep?.limits;

  if (limits && Object.keys(limits).length > 0) {
    return (
      <BudgetTable
        title={budgetTitleForKind(entity.kind)}
        used={used}
        limits={limits}
      />
    );
  }

  return <SpendSummary used={used} />;
}

export function RawTab({ value, entity, steps }: { value: unknown; entity?: TraceEntity; steps?: RunStep[] }) {
  if (!entity || !steps || entity.sourceEventIds.length === 0) {
    return <InspectorJsonBlock value={value} />;
  }

  const sourceIds = new Set(entity.sourceEventIds);
  const rawSteps = steps.filter((step) => sourceIds.has(step.id));

  if (rawSteps.length === 0) {
    return <InspectorJsonBlock value={value} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rawSteps.map((step, index) => (
        <InspectorJsonBlock
          key={step.id}
          value={{
            index,
            id: step.id,
            type: step.type,
            timestamp: step.timestamp,
            data: step.data,
          }}
        />
      ))}
    </div>
  );
}
