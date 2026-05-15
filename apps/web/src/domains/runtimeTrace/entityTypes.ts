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
  | 'orchestrator'
  | 'planner'
  | 'agent'
  | 'llm'
  | 'tool'
  | 'decision'
  | 'error'
  | 'unknown';

// ------------------------------------------------------------------
// Budget Types
// ------------------------------------------------------------------

export interface BudgetMetric {
  used: number;
  limit?: number;
}

export interface BudgetSnapshot {
  steps?: BudgetMetric;
  tools?: BudgetMetric;
  retries?: BudgetMetric;
  tokens?: BudgetMetric;
  wallTimeMs?: BudgetMetric;
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
  toolsAvailable?: string[];
  deniedTools?: string[]; // Future (after backend Stage 1)
  partialModeWarning?: string;
}

export interface PlannerData {
  kind: 'planner';
  stepKind: string; // 'call_agent' | 'direct_answer' | 'final' | 'ask_user' | 'abort' | ...
  rationale?: string;
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
  role?: 'planner' | 'synthesizer' | 'fact_extractor' | 'summary' | string;
  intent?: string;
}

export interface RunData {
  kind: 'run';
  userRequest?: string;
  agentSlug?: string;
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
  | PlannerData
  | OrchestratorData
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

  // Budget (aggregated for this entity)
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

export function isPlannerData(data: EntityData): data is PlannerData {
  return data.kind === 'planner';
}

export function isOrchestratorData(data: EntityData): data is OrchestratorData {
  return data.kind === 'orchestrator';
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
