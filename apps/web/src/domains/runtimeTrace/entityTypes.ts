/**
 * Entity Types for Hierarchical Trace
 *
 * Transform flat SemanticEvent[] into a tree of business entities.
 * Each entity represents a logical unit (run, orchestrator, agent, llm, tool, decision, error).
 */

import type { SemanticEvent } from './types';

// ------------------------------------------------------------------
// Entity Kinds
// ------------------------------------------------------------------

export type EntityKind =
  | 'run'
  | 'phase'
  | 'orchestrator'
  | 'planner'
  | 'agent'
  | 'interaction'
  | 'llm'
  | 'tool'
  | 'decision'
  | 'error'
  | 'unknown';

// ------------------------------------------------------------------
// Budget Types
// ------------------------------------------------------------------

export type BudgetMetric =
  | 'planner_steps'
  | 'agent_steps'
  | 'tool_calls'
  | 'tokens_in'
  | 'tokens_out'
  | 'tokens_total'
  | 'retries'
  | 'wall_time_ms';

export type EntityUsed = Partial<Record<BudgetMetric, number>>;
export type EntityLimits = Partial<Record<BudgetMetric, number>>;

export interface EntityBudget {
  own: EntityUsed;
  aggregated: EntityUsed;
  limits: EntityLimits | null;
  role?: string;
}

// Backward-compatible aliases used by legacy rendering paths.
export interface LegacyBudgetMetric {
  used: number;
  limit?: number | null;
  remaining?: number | null;
}
export interface BudgetSnapshot {
  steps?: LegacyBudgetMetric;
  tools?: LegacyBudgetMetric;
  retries?: LegacyBudgetMetric;
  tokens?: LegacyBudgetMetric;
  wallTimeMs?: LegacyBudgetMetric;
}
export type BudgetDelta = BudgetSnapshot;

// ------------------------------------------------------------------
// Kind-Specific Entity Data (Discriminated Union)
// ------------------------------------------------------------------

export interface LLMData {
  kind: 'llm';
  llmCallId?: string;
  parentEntityType?: string;
  parentEntityId?: string;
  purpose?: string;
  prompt?: {
    messages?: Array<Record<string, unknown>>;
    systemPrompt?: string;
    messagesHash?: string;
    systemPromptHash?: string;
    isBriefMode: boolean;
  };
  response?: {
    content?: string;
    rawResponse?: string;
    responseLength?: number;
  };
  decision?: {
    toolCalls?: Array<{
      tool: string;
      arguments: Record<string, unknown>;
      callId?: string;
    }>;
    finalAnswer?: string;
    clarifyQuestion?: string;
  };
  params?: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
    stopSequences?: string[];
  };
  tokensIn?: number;
  tokensOut?: number;
  tokensTotal?: number;
}

export interface ToolData {
  kind: 'tool';
  toolSlug: string;
  callId?: string;
  llmCallId?: string;
  calledByAgentSlug?: string;
  calledByAgentRunId?: string;
  arguments?: Record<string, unknown>;
  result?: {
    success: boolean;
    data?: unknown;
    error?: string;
    errorCode?: string;
    retryable?: boolean;
  };
  retries?: Array<{
    attempt: number;
    error?: string;
  }>;
  permissions?: {
    scope?: string;
    allowed?: string[];
    denied?: string[];
  };
}

export interface TraceContextSnapshot {
  inputs?: {
    user_request?: string;
    goal?: string;
    agent_input?: unknown;
    planner_hint?: string;
    iteration_intent?: string;
  };
  system_prompt?: string;
  system_prompt_hash?: string;
  limits?: Partial<Record<BudgetMetric, number>>;
  rbac?: {
    candidates?: string[];
    allowed?: string[];
    denied?: string[];
    reason?: Record<string, string>;
    denied_by_rbac?: string[];
    denied_by_capability?: string[];
  };
  meta?: {
    role?: string;
    model?: string;
    agent_slug?: string;
    version_label?: string;
    explicit_agent_slug?: string;
    available_operations?: string[];
    available_agents?: string[];
    components?: string[];
    attempt?: number;
    max_attempts?: number;
    memory_digest?: {
      facts?: number;
      summary_chars?: number;
    };
  };
}

export interface AgentData {
  kind: 'agent';
  slug: string;
  versionId?: string;
  versionLabel?: string;
  isDraft?: boolean;
  hasOverrides?: boolean;
  intent?: string;
  prompt?: {
    systemPrompt?: string;
    isBriefMode: boolean;
    messagesHash?: string;
  };
  contextSnapshot?: TraceContextSnapshot;
  toolsAvailable?: string[];
  deniedTools?: string[]; // Future (after backend Stage 1)
  partialModeWarning?: string;
}

export interface InteractionData {
  kind: 'interaction';
  interactionKind: 'clarify' | 'confirm' | 'resume' | string;
  question?: string;
  answer?: string;
  resumeAction?: string;
  sourceRunId?: string;
}

export interface PlannerData {
  kind: 'planner';
  stepKind: string; // 'call_agent' | 'direct_answer' | 'final' | 'ask_user' | 'abort' | ...
  rationale?: string;
  contextSnapshot?: TraceContextSnapshot;
  alternatives?: Array<{
    kind: string;
    agentSlug?: string;
    confidence?: number;
  }>;
  inputs?: {
    goal?: string;
    availableAgents?: string[];
    previousResults?: unknown[];
  };
  decision?: {
    chosenAgentSlug?: string;
    agentInput?: Record<string, unknown>;
  };
}

export interface OrchestratorData {
  kind: 'orchestrator';
  slug: string;
  role?: 'planner' | 'synthesizer' | 'memory' | 'fact_extractor' | 'summary_compactor' | 'summary' | string;
  intent?: string;
  contextSnapshot?: TraceContextSnapshot;
}

export interface PhaseData {
  kind: 'phase';
  phaseRole: 'active' | 'memory';
}

export interface RunData {
  kind: 'run';
  userRequest?: string;
  agentSlug?: string;
  contextSnapshot?: TraceContextSnapshot;
  limits?: {
    maxSteps?: number;
    maxTools?: number;
    maxWallTimeMs?: number;
    maxRetries?: number;
  };
  finalContent?: string;
  finalError?: string;
  routingDecisions?: Array<{
    agentSlug?: string;
    reason: string;
    timestamp?: string;
  }>;
}

export interface ErrorData {
  kind: 'error';
  code?: string;
  userMessage?: string;
  operatorMessage?: string;
  debug?: {
    stack?: string;
    context?: Record<string, unknown>;
  };
}

export interface UnknownData {
  kind: 'unknown';
  rawType: string;
  raw: Record<string, unknown>;
  hint: string;
}

export type EntityData =
  | LLMData
  | ToolData
  | AgentData
  | InteractionData
  | PlannerData
  | OrchestratorData
  | PhaseData
  | RunData
  | ErrorData
  | UnknownData;

// ------------------------------------------------------------------
// Trace Entity (Node in the tree)
// ------------------------------------------------------------------

export interface TraceEntity {
  // Identity
  id: string;
  kind: EntityKind;

  // Hierarchy
  parentId: string | null;
  depth: number;
  children: TraceEntity[];

  // Display
  title: string;
  status: 'ok' | 'warn' | 'error' | 'info' | 'pending';

  // Timing
  startedAt?: string;
  durationMs?: number;

  // Budget (new model)
  budget?: EntityBudget;
  // Legacy fields (to be removed after full migration)
  budgetSnapshot?: BudgetSnapshot;
  budgetDelta?: BudgetDelta;

  // Source mapping (which SemanticEvents contributed to this entity)
  sourceEventIds: string[];

  // Kind-specific data
  data: EntityData;
}

// ------------------------------------------------------------------
// Sub-Agent Run (for linking parent-child runs)
// ------------------------------------------------------------------

export interface SubAgentRun {
  runId: string;
  parentRunId: string;
  parentEntityId?: string; // Which agent entity in parent triggered this sub-agent
  agentSlug: string;
  events: SemanticEvent[];
  status: 'ok' | 'warn' | 'error';
  startedAt?: string;
  durationMs?: number;
}

// ------------------------------------------------------------------
// Tree Builder Options
// ------------------------------------------------------------------

export interface BuildEntityTreeOptions {
  /** If true, treat sub-agent runs as separate children entities (requires backend Stage 1) */
  linkSubAgents?: boolean;
  /** Sub-agent runs to merge into the tree (empty if linkSubAgents=false or backend not ready) */
  subAgentRuns?: SubAgentRun[];
  /** Optional sink for step-by-step container assembly debug records */
  debugRecords?: ContainerDebugRecord[];
}

export interface ContainerDebugRecord {
  eventId: string;
  rawType: string;
  phase: string;
  action: string;
  entityId?: string;
  entityKind?: EntityKind;
  note?: string;
}

// ------------------------------------------------------------------
// Helper type guards
// ------------------------------------------------------------------

export function isLLMData(data: EntityData): data is LLMData {
  return data.kind === 'llm';
}

export function isToolData(data: EntityData): data is ToolData {
  return data.kind === 'tool';
}

export function isAgentData(data: EntityData): data is AgentData {
  return data.kind === 'agent';
}

export function isInteractionData(data: EntityData): data is InteractionData {
  return data.kind === 'interaction';
}

export function isPlannerData(data: EntityData): data is PlannerData {
  return data.kind === 'planner';
}

export function isOrchestratorData(data: EntityData): data is OrchestratorData {
  return data.kind === 'orchestrator';
}

export function isPhaseData(data: EntityData): data is PhaseData {
  return data.kind === 'phase';
}

export function isRunData(data: EntityData): data is RunData {
  return data.kind === 'run';
}

export function isErrorData(data: EntityData): data is ErrorData {
  return data.kind === 'error';
}

export function isUnknownData(data: EntityData): data is UnknownData {
  return data.kind === 'unknown';
}
