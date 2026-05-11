/**
 * Trace Aggregator v2
 *
 * Converts flat SemanticEvent[] (from backend) into AggregatedRun:
 *   - RunInput  — context given to the agent before execution
 *   - TraceEntry[] — logical actions with running budget state
 *   - RunFinal  — final result
 */
import type { RunTrace, SemanticEvent } from './types';

// ─── Budget ────────────────────────────────────────────────────────────────

export interface BudgetLimits {
  maxSteps?: number;
  maxTools?: number;
  maxRetries?: number;
  toolTimeoutMs?: number;
  wallTimeMs?: number;
}

export interface BudgetState {
  steps: { used: number; limit: number };
  tools: { used: number; limit: number };
  retries: { used: number; limit: number };
  tokens?: { used: number; limit?: number };
}

function zeroBudget(limits: BudgetLimits): BudgetState {
  return {
    steps: { used: 0, limit: limits.maxSteps ?? 0 },
    tools: { used: 0, limit: limits.maxTools ?? 0 },
    retries: { used: 0, limit: limits.maxRetries ?? 0 },
  };
}

// ─── Input ─────────────────────────────────────────────────────────────────

export interface RunInput {
  userRequest: string;
  limits: BudgetLimits;
  agent?: { slug?: string; versionId?: string; loggingLevel?: string };
  tools?: Array<{ slug: string; releaseId?: string }>;
  model?: string;
}

// ─── Retry ─────────────────────────────────────────────────────────────────

export interface RetryAttempt {
  reason: string;
  error?: string;
  startedAt?: string;
}

// ─── Trace Entries ─────────────────────────────────────────────────────────

export interface BaseMeta {
  id: string;
  startedAt?: string;
  durationMs?: number;
  budgetSnapshot: BudgetState;
  rawEvents: SemanticEvent[];
}

export interface LLMTraceEntry extends BaseMeta {
  type: 'llm';
  intent: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  messages?: unknown[];
  responseContent?: string;
  tokensIn?: number;
  tokensOut?: number;
  isBriefMode?: boolean;
}

export interface ToolTraceEntry extends BaseMeta {
  type: 'tool';
  toolName: string;
  operationSlug?: string;
  input?: unknown;
  output?: unknown;
  status: 'success' | 'failed' | 'pending';
  retries: RetryAttempt[];
}

export interface DecisionTraceEntry extends BaseMeta {
  type: 'decision';
  kind: string;
  summary: string;
  details?: Record<string, unknown>;
}

export interface ErrorTraceEntry extends BaseMeta {
  type: 'error';
  code: string;
  userMessage?: string;
  operatorMessage?: string;
  debug?: unknown;
}

export type TraceEntry =
  | LLMTraceEntry
  | ToolTraceEntry
  | DecisionTraceEntry
  | ErrorTraceEntry;

// ─── Final ─────────────────────────────────────────────────────────────────

export interface RunFinal {
  status: 'completed' | 'failed' | 'stopped' | 'running';
  answer?: string;
  error?: { code?: string; userMessage?: string; operatorMessage?: string };
  startedAt?: string;
}

// ─── Aggregated Run ────────────────────────────────────────────────────────

export interface AggregatedRun {
  input: RunInput;
  traceEntries: TraceEntry[];
  final: RunFinal;
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

function extractLimits(event: SemanticEvent): BudgetLimits {
  const d = event.raw.raw;
  return {
    maxSteps: d.max_steps != null ? Number(d.max_steps) : undefined,
    maxTools: d.max_tool_calls_total != null ? Number(d.max_tool_calls_total) : undefined,
    maxRetries: d.max_retries != null ? Number(d.max_retries) : undefined,
    toolTimeoutMs: d.tool_timeout_ms != null ? Number(d.tool_timeout_ms) : undefined,
    wallTimeMs: d.max_wall_time_ms != null ? Number(d.max_wall_time_ms) : undefined,
  };
}

function extractIntent(event: SemanticEvent): string {
  const d = event.raw.raw;
  // Try explicit intent fields first
  const intent = d.intent ?? d.task ?? d.goal;
  if (typeof intent === 'string' && intent.trim()) return intent.trim();
  // Fall back to first user message content
  const messages = d.messages ?? d.messages_sent;
  if (Array.isArray(messages)) {
    for (const msg of messages) {
      const m = asRecord(msg);
      if (m.role === 'user' && typeof m.content === 'string' && m.content.trim()) {
        return m.content.trim().slice(0, 200);
      }
    }
  }
  // Fall back to summary
  if (event.summary && event.summary !== 'model=unknown') return event.summary;
  return 'LLM call';
}

function cloneBudget(b: BudgetState): BudgetState {
  return {
    steps: { ...b.steps },
    tools: { ...b.tools },
    retries: { ...b.retries },
    tokens: b.tokens ? { ...b.tokens } : undefined,
  };
}

// ─── Main Aggregator ───────────────────────────────────────────────────────

export function aggregateRun(
  trace: RunTrace,
  runMeta?: {
    status?: string;
    agentSlug?: string;
    loggingLevel?: string;
    contextSnapshot?: {
      model?: string;
      tools?: Array<{ slug: string; instance_id?: string }>;
    };
  },
): AggregatedRun {
  // Flatten all events and sort by actual timestamp to ensure chronological order across iterations
  const allEvents: SemanticEvent[] = trace.iterations
    .flatMap((it) => it.events)
    .sort((a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime());

  // ── 1. Extract Input ──────────────────────────────────────────────────────
  const userReqEvent = allEvents.find((e) => e.raw_type === 'user_request');
  const budgetEvent = allEvents.find(
    (e) => e.raw_type === 'budget_policy' || e.raw_type === 'budget_init',
  );

  const limits: BudgetLimits = budgetEvent ? extractLimits(budgetEvent) : {};
  const userRequest = userReqEvent
    ? String(userReqEvent.raw.raw.content ?? userReqEvent.raw.raw.request ?? userReqEvent.summary ?? '')
    : '';

  const input: RunInput = {
    userRequest,
    limits,
    agent: {
      slug: runMeta?.agentSlug,
      loggingLevel: runMeta?.loggingLevel,
    },
    tools: runMeta?.contextSnapshot?.tools?.map((t) => ({ slug: t.slug })),
    model: runMeta?.contextSnapshot?.model,
  };

  // ── 2. Build TraceEntries ─────────────────────────────────────────────────
  const entries: TraceEntry[] = [];
  let budget = zeroBudget(limits);

  // Filter out input/budget-init/final events — they go to Input/Final blocks
  const traceEvents = allEvents.filter(
    (e) =>
      e.raw_type !== 'user_request' &&
      e.raw_type !== 'budget_policy' &&
      e.raw_type !== 'budget_init' &&
      e.raw_type !== 'final' &&
      e.raw_type !== 'final_response' &&
      e.category !== 'system',
  );

  let i = 0;
  while (i < traceEvents.length) {
    const ev = traceEvents[i];
    const raw = ev.raw.raw;

    // ── LLM call: llm_request or llm_call ──
    if (ev.raw_type === 'llm_request' || ev.raw_type === 'llm_call') {
      budget = cloneBudget(budget);
      budget.steps.used += 1;

      const entry: LLMTraceEntry = {
        type: 'llm',
        id: ev.id,
        startedAt: ev.started_at,
        durationMs: ev.duration_ms,
        budgetSnapshot: cloneBudget(budget),
        rawEvents: [ev],
        intent: extractIntent(ev),
        model: String(raw.model ?? raw.provider_model ?? ''),
        temperature: raw.temperature != null ? Number(raw.temperature) : undefined,
        maxTokens: raw.max_tokens != null ? Number(raw.max_tokens) : undefined,
        messages: Array.isArray(raw.messages ?? raw.messages_sent)
          ? (raw.messages ?? raw.messages_sent) as unknown[]
          : undefined,
        isBriefMode: raw.messages_hash != null || raw.system_prompt_hash != null,
      };

      // Attach adjacent llm_response (and optionally llm_call summary after it)
      i += 1;
      if (i < traceEvents.length && traceEvents[i].raw_type === 'llm_response') {
        const resp = traceEvents[i];
        const r = resp.raw.raw;
        entry.responseContent = String(r.content ?? r.response ?? r.raw_response ?? '');
        entry.tokensIn = r.tokens_in != null ? Number(r.tokens_in) : undefined;
        entry.tokensOut = r.tokens_out != null ? Number(r.tokens_out) : undefined;
        entry.durationMs = resp.duration_ms ?? entry.durationMs;
        entry.rawEvents.push(resp);
        i += 1;
        // Skip trailing llm_call summary that duplicates the same step
        if (i < traceEvents.length && traceEvents[i].raw_type === 'llm_call') {
          i += 1;
        }
      } else if (i < traceEvents.length && traceEvents[i].raw_type === 'llm_call') {
        // llm_call without preceding llm_response — use it for response metadata
        const r = traceEvents[i].raw.raw;
        entry.responseContent = String(r.content ?? r.response ?? '');
        entry.durationMs = traceEvents[i].duration_ms ?? entry.durationMs;
        entry.rawEvents.push(traceEvents[i]);
        i += 1;
      }

      entries.push(entry);
      continue;
    }

    // Standalone llm_response without llm_request — attach to last llm entry
    if (ev.raw_type === 'llm_response') {
      const lastLlm = [...entries].reverse().find((e) => e.type === 'llm') as LLMTraceEntry | undefined;
      if (lastLlm && !lastLlm.responseContent) {
        const r = raw;
        lastLlm.responseContent = String(r.content ?? r.response ?? r.raw_response ?? '');
        lastLlm.tokensIn = r.tokens_in != null ? Number(r.tokens_in) : undefined;
        lastLlm.tokensOut = r.tokens_out != null ? Number(r.tokens_out) : undefined;
        lastLlm.rawEvents.push(ev);
      }
      i += 1;
      continue;
    }

    // ── Tool call: operation_call or tool_call ──
    if (ev.raw_type === 'operation_call' || ev.raw_type === 'tool_call') {
      budget = cloneBudget(budget);
      budget.tools.used += 1;

      const toolName = String(raw.operation_slug ?? raw.tool ?? raw.operation ?? raw.slug ?? 'tool');
      const entry: ToolTraceEntry = {
        type: 'tool',
        id: ev.id,
        startedAt: ev.started_at,
        durationMs: ev.duration_ms,
        budgetSnapshot: cloneBudget(budget),
        rawEvents: [ev],
        toolName,
        operationSlug: String(raw.operation_slug ?? raw.slug ?? toolName),
        input: raw.arguments ?? raw.parameters ?? raw.input ?? raw.payload,
        status: 'pending',
        retries: [],
      };

      // Consume adjacent protocol_retry + operation_result
      i += 1;
      while (i < traceEvents.length) {
        const next = traceEvents[i];
        if (next.raw_type === 'protocol_retry') {
          budget.retries.used += 1;
          const nr = next.raw.raw;
          entry.retries.push({
            reason: String(nr.reason ?? nr.error ?? 'retry'),
            error: nr.error ? String(nr.error) : undefined,
            startedAt: next.started_at,
          });
          entry.rawEvents.push(next);
          i += 1;
        } else if (next.raw_type === 'operation_result' || next.raw_type === 'tool_result') {
          const nr = next.raw.raw;
          // In brief mode result/output are replaced with result_hash — keep raw if available
          entry.output = nr.result ?? nr.output ?? nr.data ?? null;
          if (entry.output === null && (nr.result_hash || nr.output_hash)) {
            entry.output = { _brief: true, hash: String(nr.result_hash ?? nr.output_hash ?? ''), length: nr.result_length ?? nr.output_length };
          }
          entry.status = nr.success === false ? 'failed' : 'success';
          entry.durationMs =
            next.started_at && entry.startedAt
              ? (new Date(next.started_at).getTime() - new Date(entry.startedAt).getTime()) + (next.duration_ms ?? 0)
              : next.duration_ms ?? entry.durationMs;
          entry.rawEvents.push(next);
          i += 1;
          break;
        } else {
          break;
        }
      }

      if (entry.status === 'pending') entry.status = 'failed';
      entries.push(entry);
      continue;
    }

    // Standalone result without a preceding call — skip gracefully
    if (ev.raw_type === 'operation_result' || ev.raw_type === 'tool_result') {
      i += 1;
      continue;
    }

    // ── Decision / routing / planner ──
    if (ev.category === 'decision' || ev.category === 'planner' || ev.category === 'policy') {
      entries.push({
        type: 'decision',
        id: ev.id,
        startedAt: ev.started_at,
        durationMs: ev.duration_ms,
        budgetSnapshot: cloneBudget(budget),
        rawEvents: [ev],
        kind: ev.raw_type,
        summary: ev.summary,
        details: ev.decision ?? ev.raw.raw,
      });
      i += 1;
      continue;
    }

    // ── Budget consumed / exceeded (mid-run) ──
    if (ev.category === 'budget') {
      const r = raw;
      // Update running budget from consumed event
      if (r.used != null || r.consumed != null || r.steps_used != null) {
        const used = Number(r.consumed ?? r.used ?? r.steps_used ?? 0);
        if (used > budget.steps.used) budget.steps.used = used;
      }
      i += 1;
      continue;
    }

    // ── Retry (standalone) ──
    if (ev.category === 'retry') {
      budget.retries.used += 1;
      i += 1;
      continue;
    }

    // ── Error ──
    if (ev.category === 'error') {
      const r = raw;
      entries.push({
        type: 'error',
        id: ev.id,
        startedAt: ev.started_at,
        durationMs: ev.duration_ms,
        budgetSnapshot: cloneBudget(budget),
        rawEvents: [ev],
        code: String(r.code ?? r.error ?? 'error'),
        userMessage: r.user_message ? String(r.user_message) : undefined,
        operatorMessage: r.operator_message ? String(r.operator_message) : undefined,
        debug: r.debug,
      });
      i += 1;
      continue;
    }

    i += 1;
  }

  // ── 3. Extract Final ───────────────────────────────────────────────────────
  const finalEvent = allEvents.find(
    (e) => e.raw_type === 'final' || e.raw_type === 'final_response',
  );
  const errorEvent = allEvents.find((e) => e.raw_type === 'error');
  const runStatus = (runMeta?.status ?? 'completed') as RunFinal['status'];

  const finalAnswer = finalEvent
    ? String(finalEvent.raw.raw.content ?? finalEvent.raw.raw.answer ?? finalEvent.summary ?? '')
    : undefined;

  const finalError = errorEvent
    ? {
        code: String(errorEvent.raw.raw.code ?? 'error'),
        userMessage: errorEvent.raw.raw.user_message ? String(errorEvent.raw.raw.user_message) : undefined,
        operatorMessage: errorEvent.raw.raw.operator_message ? String(errorEvent.raw.raw.operator_message) : undefined,
      }
    : undefined;

  return {
    input,
    traceEntries: entries,
    final: {
      status: runStatus,
      answer: finalAnswer,
      error: finalError,
      startedAt: finalEvent?.started_at,
    },
  };
}
