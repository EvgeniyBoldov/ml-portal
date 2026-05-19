import type { BudgetDelta, BudgetMetric, BudgetSnapshot, EntityUsed, TraceEntity } from './entityTypes';
import type { SemanticEvent } from './types';
import { parseBudgetSnapshot } from './budget';

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

function toLegacyMetric(used: number, limit?: number): { used: number; limit?: number } {
  if (limit === undefined) return { used };
  return { used, limit };
}

function toLegacySnapshot(used: EntityUsed, limits: Record<string, number> = {}): BudgetSnapshot {
  return {
    steps: (used.planner_steps || used.agent_steps) ? toLegacyMetric(Math.max(Number(used.planner_steps ?? 0), Number(used.agent_steps ?? 0)), limits.planner_steps ?? limits.agent_steps) : undefined,
    tools: used.tool_calls ? toLegacyMetric(Number(used.tool_calls), limits.tool_calls) : undefined,
    retries: used.retries ? toLegacyMetric(Number(used.retries), limits.retries) : undefined,
    tokens: used.tokens_total ? toLegacyMetric(Number(used.tokens_total), limits.tokens_total) : undefined,
    wallTimeMs: used.wall_time_ms ? toLegacyMetric(Number(used.wall_time_ms), limits.wall_time_ms) : undefined,
  };
}

function sumUsed(a: EntityUsed, b: EntityUsed): EntityUsed {
  const out: EntityUsed = { ...a };
  for (const m of METRICS) {
    const v = Number(b[m] ?? 0);
    if (v > 0) out[m] = Number(out[m] ?? 0) + v;
  }
  return out;
}

export function applyBudgetSnapshots(entityById: Map<string, TraceEntity>, events: SemanticEvent[]): void {
  for (const event of events) {
    if (event.raw_type !== 'budget_snapshot') continue;
    const raw = ((event.budget as Record<string, unknown> | undefined) ?? (event.raw?.raw ?? {})) as Record<string, unknown>;
    const parsed = parseBudgetSnapshot(raw);
    if (!parsed) continue;
    const entity = entityById.get(parsed.entityId);
    if (!entity) continue;
    entity.budget = {
      own: parsed.own,
      aggregated: parsed.own,
      limits: parsed.limits,
      role: parsed.role,
    };
    entity.budgetSnapshot = toLegacySnapshot(parsed.own, parsed.limits ?? {});
  }
}

export function aggregateBudgetsBottomUp(entity: TraceEntity): EntityUsed {
  const own = entity.budget?.own ?? {};
  let aggregated: EntityUsed = { ...own };
  for (const child of entity.children) {
    const childAgg = aggregateBudgetsBottomUp(child);
    aggregated = sumUsed(aggregated, childAgg);
  }

  const hasNewBudget = Boolean(entity.budget);
  const hasAnyAggregated = METRICS.some((m) => Number(aggregated[m] ?? 0) > 0);
  if (hasNewBudget || hasAnyAggregated) {
    entity.budget = {
      own,
      aggregated,
      limits: entity.budget?.limits ?? null,
      role: entity.budget?.role,
    };
    entity.budgetSnapshot = toLegacySnapshot(aggregated, entity.budget?.limits ?? {});
  }

  return aggregated;
}

// ------------------------------------------------------------------
// Backward-compatible legacy exports
// ------------------------------------------------------------------

export function extractBudgetSnapshot(event: SemanticEvent): BudgetSnapshot | undefined {
  if (event.raw_type !== 'budget_snapshot') return undefined;
  const raw = ((event.budget as Record<string, unknown> | undefined) ?? (event.raw?.raw ?? {})) as Record<string, unknown>;
  const parsed = parseBudgetSnapshot(raw);
  if (!parsed) return undefined;
  return toLegacySnapshot(parsed.own, parsed.limits ?? {});
}

export function extractBudgetDelta(event: SemanticEvent): BudgetDelta | undefined {
  if (event.raw_type !== 'budget_snapshot') return undefined;
  const raw = ((event.budget as Record<string, unknown> | undefined) ?? (event.raw?.raw ?? {})) as Record<string, unknown>;
  const parsed = parseBudgetSnapshot(raw);
  if (!parsed) return undefined;
  return toLegacySnapshot(parsed.delta, parsed.limits ?? {});
}

export function mergeBudgetSnapshots(a: BudgetSnapshot, b: BudgetSnapshot): BudgetSnapshot {
  return {
    steps: b.steps ?? a.steps,
    tools: b.tools ?? a.tools,
    retries: b.retries ?? a.retries,
    tokens: b.tokens ?? a.tokens,
    wallTimeMs: b.wallTimeMs ?? a.wallTimeMs,
  };
}

export function sumBudgetDeltas(a: BudgetDelta, b: BudgetDelta): BudgetDelta {
  const add = (x?: { used: number; limit?: number | null }, y?: { used: number; limit?: number | null }) => {
    if (!x && !y) return undefined;
    return { used: Number(x?.used ?? 0) + Number(y?.used ?? 0), limit: y?.limit ?? x?.limit };
  };
  return {
    steps: add(a.steps, b.steps),
    tools: add(a.tools, b.tools),
    retries: add(a.retries, b.retries),
    tokens: add(a.tokens, b.tokens),
    wallTimeMs: add(a.wallTimeMs, b.wallTimeMs),
  };
}

export function collectBudgetFromEvents(events: SemanticEvent[]): BudgetSnapshot | undefined {
  let acc: BudgetSnapshot = {};
  for (const event of events) {
    const snap = extractBudgetSnapshot(event);
    if (!snap) continue;
    acc = mergeBudgetSnapshots(acc, snap);
  }
  return Object.keys(acc).length > 0 ? acc : undefined;
}

export function computeAggregateBudgets(entity: TraceEntity): void {
  const fromLegacy = (node: TraceEntity): void => {
    if (!node.budget && node.budgetSnapshot) {
      node.budget = {
        own: {
          planner_steps: Number(node.budgetSnapshot.steps?.used ?? 0),
          tool_calls: Number(node.budgetSnapshot.tools?.used ?? 0),
          retries: Number(node.budgetSnapshot.retries?.used ?? 0),
          tokens_total: Number(node.budgetSnapshot.tokens?.used ?? 0),
          wall_time_ms: Number(node.budgetSnapshot.wallTimeMs?.used ?? 0),
        },
        aggregated: {},
        limits: {
          planner_steps: typeof node.budgetSnapshot.steps?.limit === 'number' ? node.budgetSnapshot.steps.limit : undefined,
          tool_calls: typeof node.budgetSnapshot.tools?.limit === 'number' ? node.budgetSnapshot.tools.limit : undefined,
          retries: typeof node.budgetSnapshot.retries?.limit === 'number' ? node.budgetSnapshot.retries.limit : undefined,
          tokens_total: typeof node.budgetSnapshot.tokens?.limit === 'number' ? node.budgetSnapshot.tokens.limit : undefined,
          wall_time_ms: typeof node.budgetSnapshot.wallTimeMs?.limit === 'number' ? node.budgetSnapshot.wallTimeMs.limit : undefined,
        },
      };
    }
    node.children.forEach(fromLegacy);
  };
  fromLegacy(entity);
  aggregateBudgetsBottomUp(entity);
}
