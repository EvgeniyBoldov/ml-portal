/**
 * Runtime Trace Domain
 *
 * Provides utilities for:
 * - Normalizing raw trace steps to semantic events
 * - Building hierarchical entity trees from flat events
 * - Budget tracking and aggregation
 */

// Core types
export type {
  RunTrace,
  SemanticEvent,
  TraceCategory,
  TraceIteration,
  TraceSourceStep,
  TraceStatus,
  RawEventRef,
} from './types';

// Entity types (Stage 2)
export type {
  AgentData,
  BudgetDelta,
  BudgetMetric,
  BudgetSnapshot,
  BuildEntityTreeOptions,
  EntityData,
  EntityKind,
  ErrorData,
  LLMData,
  OrchestratorData,
  PlannerData,
  RunData,
  SubAgentRun,
  ToolData,
  TraceEntity,
  UnknownData,
} from './entityTypes';

export {
  isAgentData,
  isErrorData,
  isLLMData,
  isOrchestratorData,
  isPlannerData,
  isRunData,
  isToolData,
  isUnknownData,
} from './entityTypes';

// Tree builder (Stage 3)
export {
  buildEntityTree,
  findEntityById,
  flattenEntityTree,
  getEntityPath,
} from './buildEntityTree';

// Normalizers
export { buildRunTrace, normalizeTraceEvent } from './normalize';

// Budget UI (Stage 6)
export { BudgetPill, BudgetPills, BudgetTable } from './budget';

// Artifacts (existing)
export { extractTraceArtifacts } from './artifacts';
export type { TraceArtifacts } from './artifacts';
