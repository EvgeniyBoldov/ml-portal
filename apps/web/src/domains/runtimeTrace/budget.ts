import type { BudgetMetric, EntityLimits, EntityUsed } from './entityTypes';

export interface ParsedBudgetSnapshot {
  entityType: string;
  entityId: string;
  parentEntityId?: string;
  role?: string;
  own: EntityUsed;
  limits: EntityLimits | null;
  delta: EntityUsed;
  reason: string;
  atMs: number;
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

function metricValue(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

function parseUsed(obj: unknown): EntityUsed {
  if (!obj || typeof obj !== 'object') return {};
  const src = obj as Record<string, unknown>;
  const out: EntityUsed = {};
  for (const key of METRICS) {
    const val = metricValue(src[key]);
    if (val !== undefined) out[key] = val;
  }
  return out;
}

export function parseBudgetSnapshot(data: Record<string, unknown>): ParsedBudgetSnapshot | null {
  const entityId = typeof data.entity_id === 'string' ? data.entity_id : undefined;
  const entityType = typeof data.entity_type === 'string' ? data.entity_type : undefined;
  const legacySnapshot = (data.snapshot && typeof data.snapshot === 'object') ? (data.snapshot as Record<string, unknown>) : null;
  const legacyOwnerId = typeof data.owner_id === 'string' ? data.owner_id : undefined;
  const legacyOwnerScope = typeof data.owner_scope === 'string' ? data.owner_scope : undefined;

  const normalizedEntityId = entityId ?? legacyOwnerId;
  const normalizedEntityType = entityType ?? legacyOwnerScope;
  if (!normalizedEntityId || !normalizedEntityType) return null;

  const own = parseUsed(data.own);
  if (legacySnapshot) {
    const legacyToMetric: Array<[keyof typeof legacySnapshot, BudgetMetric]> = [
      ['planner_iterations', 'planner_steps'],
      ['agent_steps', 'agent_steps'],
      ['tool_calls', 'tool_calls'],
      ['tokens_in', 'tokens_in'],
      ['tokens_out', 'tokens_out'],
      ['tokens_total', 'tokens_total'],
      ['retries', 'retries'],
      ['wall_time_ms', 'wall_time_ms'],
    ];
    for (const [legacyKey, metric] of legacyToMetric) {
      const metricObj = legacySnapshot[legacyKey];
      if (metricObj && typeof metricObj === 'object') {
        const usedVal = metricValue((metricObj as Record<string, unknown>).used);
        if (usedVal !== undefined) own[metric] = usedVal;
      }
    }
  }

  const delta = parseUsed(data.delta);
  let limits: EntityLimits | null = null;
  if (data.limits && typeof data.limits === 'object') {
    limits = parseUsed(data.limits);
  } else if (legacySnapshot) {
    const legacyLimits: EntityLimits = {};
    const legacyToMetric: Array<[keyof typeof legacySnapshot, BudgetMetric]> = [
      ['planner_iterations', 'planner_steps'],
      ['agent_steps', 'agent_steps'],
      ['tool_calls', 'tool_calls'],
      ['tokens_total', 'tokens_total'],
      ['retries', 'retries'],
      ['wall_time_ms', 'wall_time_ms'],
    ];
    for (const [legacyKey, metric] of legacyToMetric) {
      const metricObj = legacySnapshot[legacyKey];
      if (metricObj && typeof metricObj === 'object') {
        const limitVal = metricValue((metricObj as Record<string, unknown>).limit);
        if (limitVal !== undefined) legacyLimits[metric] = limitVal;
      }
    }
    limits = Object.keys(legacyLimits).length > 0 ? legacyLimits : null;
  }

  return {
    entityType: normalizedEntityType,
    entityId: normalizedEntityId,
    parentEntityId: typeof data.parent_entity_id === 'string' ? data.parent_entity_id : undefined,
    role: typeof data.role === 'string' ? data.role : undefined,
    own,
    limits,
    delta,
    reason: typeof data.reason === 'string' ? data.reason : 'snapshot',
    atMs: typeof data.at_ms === 'number' ? data.at_ms : 0,
  };
}

export { BudgetPills, BudgetTable } from './budgetUi';
export { SpendSummary } from './SpendSummary';
