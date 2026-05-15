import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock } from '@/shared/ui/Inspector';
import type { BudgetSnapshot, TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import { BudgetTable } from '@/domains/runtimeTrace/budget';
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

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
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

function mergeMetric(
  base: BudgetSnapshot[keyof BudgetSnapshot],
  next: BudgetSnapshot[keyof BudgetSnapshot],
) {
  if (!base) return next;
  if (!next) return base;
  return {
    used: Math.max(base.used, next.used),
    limit: next.limit ?? base.limit,
  };
}

function extractBudgetFromStep(step: RunStep): BudgetSnapshot | undefined {
  const d = step.data as Record<string, unknown>;
  const raw =
    toRecord(d.shared_budget)
    ?? toRecord(d.runtime_budget)
    ?? toRecord(d.budget)
    ?? d;

  const snap: BudgetSnapshot = {};

  const stepsRaw = toRecord(raw.steps);
  const toolsRaw = toRecord(raw.tools);
  const retriesRaw = toRecord(raw.retries);
  const tokensRaw = toRecord(raw.tokens);
  const wallRaw = toRecord(raw.wallTimeMs);

  const stepsUsed = num(stepsRaw?.used) ?? num(raw.consumed_planner_iterations);
  const stepsLimit = num(stepsRaw?.limit) ?? num(raw.max_planner_iterations) ?? num(raw.max_steps);
  if (stepsUsed !== undefined || stepsLimit !== undefined) snap.steps = { used: stepsUsed ?? 0, limit: stepsLimit };

  const toolsUsed = num(toolsRaw?.used) ?? num(raw.consumed_tool_calls);
  const toolsLimit = num(toolsRaw?.limit) ?? num(raw.max_tool_calls_total);
  if (toolsUsed !== undefined || toolsLimit !== undefined) snap.tools = { used: toolsUsed ?? 0, limit: toolsLimit };

  const retriesUsed = num(retriesRaw?.used) ?? num(raw.retries);
  const retriesLimit = num(retriesRaw?.limit);
  if (retriesUsed !== undefined || retriesLimit !== undefined) snap.retries = { used: retriesUsed ?? 0, limit: retriesLimit };

  const tokensUsed = num(tokensRaw?.used) ?? num(raw.tokens_consumed) ?? num(raw.tokens_in);
  const tokensLimit = num(tokensRaw?.limit) ?? num(raw.tokens_limit);
  if (tokensUsed !== undefined || tokensLimit !== undefined) snap.tokens = { used: tokensUsed ?? 0, limit: tokensLimit };

  const wallUsed = num(wallRaw?.used)
    ?? ((num(raw.max_wall_time_ms) !== undefined && num(raw.remaining_wall_time_ms) !== undefined)
      ? Math.max(0, (num(raw.max_wall_time_ms) ?? 0) - (num(raw.remaining_wall_time_ms) ?? 0))
      : undefined);
  const wallLimit = num(wallRaw?.limit) ?? num(raw.max_wall_time_ms);
  if (wallUsed !== undefined || wallLimit !== undefined) snap.wallTimeMs = { used: wallUsed ?? 0, limit: wallLimit };

  return Object.keys(snap).length > 0 ? snap : undefined;
}

function aggregateBudgetFromSteps(entity: TraceEntity, steps: RunStep[]): BudgetSnapshot | undefined {
  const sourceIds = new Set<string>();
  const collectIds = (node: TraceEntity) => {
    node.sourceEventIds.forEach((id) => sourceIds.add(id));
    node.children.forEach(collectIds);
  };
  collectIds(entity);

  const related = steps.filter((step) => sourceIds.has(step.id));
  if (related.length === 0) return undefined;

  let acc: BudgetSnapshot = {};
  for (const step of related) {
    const snap = extractBudgetFromStep(step);
    if (!snap) continue;
    acc.steps = mergeMetric(acc.steps, snap.steps);
    acc.tools = mergeMetric(acc.tools, snap.tools);
    acc.retries = mergeMetric(acc.retries, snap.retries);
    acc.tokens = mergeMetric(acc.tokens, snap.tokens);
    acc.wallTimeMs = mergeMetric(acc.wallTimeMs, snap.wallTimeMs);
  }

  return Object.keys(acc).length > 0 ? acc : undefined;
}

function diffMetric(
  before: BudgetSnapshot[keyof BudgetSnapshot],
  after: BudgetSnapshot[keyof BudgetSnapshot],
): BudgetSnapshot[keyof BudgetSnapshot] {
  if (!after && !before) return undefined;
  const afterUsed = after?.used ?? 0;
  const beforeUsed = before?.used ?? 0;
  return {
    used: Math.max(0, afterUsed - beforeUsed),
    limit: after?.limit ?? before?.limit,
  };
}

function buildDeltaFromSnapshots(before: BudgetSnapshot, after: BudgetSnapshot): BudgetSnapshot {
  return {
    steps: diffMetric(before.steps, after.steps),
    tools: diffMetric(before.tools, after.tools),
    retries: diffMetric(before.retries, after.retries),
    tokens: diffMetric(before.tokens, after.tokens),
    wallTimeMs: diffMetric(before.wallTimeMs, after.wallTimeMs),
  };
}

function plannerBudgetFromWindow(entity: TraceEntity, steps: RunStep[]): { snapshot?: BudgetSnapshot; delta?: BudgetSnapshot } {
  if (entity.sourceEventIds.length === 0 || steps.length === 0) return {};

  const ids = new Set(entity.sourceEventIds);
  const indices = steps
    .map((step, idx) => (ids.has(step.id) ? idx : -1))
    .filter((idx) => idx >= 0);
  if (indices.length === 0) return {};

  const start = Math.min(...indices);
  const end = Math.max(...indices);

  let before: BudgetSnapshot | undefined;
  for (let i = start; i >= 0; i--) {
    const snap = extractBudgetFromStep(steps[i]);
    if (snap) {
      before = snap;
      break;
    }
  }

  let after: BudgetSnapshot | undefined;
  for (let i = end; i < steps.length; i++) {
    const snap = extractBudgetFromStep(steps[i]);
    if (snap) {
      after = snap;
      break;
    }
  }

  if (!after && before) return { snapshot: before };
  if (!after) return {};
  if (!before) return { snapshot: after };

  return {
    snapshot: after,
    delta: buildDeltaFromSnapshots(before, after),
  };
}

function budgetTitleForKind(kind: TraceEntity['kind']): string {
  if (kind === 'agent') return 'Бюджет агента';
  if (kind === 'planner' || kind === 'decision' || kind === 'orchestrator') return 'Бюджет планирования';
  if (kind === 'tool') return 'Бюджет инструмента';
  if (kind === 'run') return 'Бюджет запуска';
  return 'Использование бюджета';
}

export function BudgetsTab({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const fallbackSnapshot = aggregateBudgetFromSteps(entity, steps);
  const plannerWindow = entity.kind === 'planner' ? plannerBudgetFromWindow(entity, steps) : {};

  const snapshot = entity.kind === 'planner'
    ? (plannerWindow.snapshot ?? entity.budgetSnapshot ?? fallbackSnapshot)
    : (entity.budgetSnapshot ?? fallbackSnapshot ?? plannerWindow.snapshot);
  const delta = entity.kind === 'planner'
    ? (plannerWindow.delta ?? entity.budgetDelta)
    : (entity.budgetDelta ?? plannerWindow.delta);

  return (
    <BudgetTable
      snapshot={snapshot}
      delta={delta}
      title={budgetTitleForKind(entity.kind)}
    />
  );
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
