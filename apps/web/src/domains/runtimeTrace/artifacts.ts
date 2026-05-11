import type { SemanticEvent } from './types';

export interface TraceArtifacts {
  prompt?: unknown;
  llmRequest?: unknown;
  llmRawResponse?: unknown;
  llmParsedResponse?: unknown;
  validation?: unknown;
  budget?: unknown;
  decision?: unknown;
  operationInput?: unknown;
  operationOutput?: unknown;
  errorContract?: unknown;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function pickFirst(data: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (data[key] !== undefined) return data[key];
  }
  return undefined;
}

function compactRecord(source: Record<string, unknown>): Record<string, unknown> | undefined {
  const entries = Object.entries(source).filter(([, value]) => value !== undefined && value !== null);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries);
}

export function extractTraceArtifacts(event: SemanticEvent): TraceArtifacts {
  const raw = asRecord(event.raw?.raw);
  const artifacts: TraceArtifacts = {};

  const prompt = pickFirst(raw, ['compiled_prompt', 'system_prompt', 'prompt', 'resolved_prompt']);
  if (prompt !== undefined) artifacts.prompt = prompt;

  const llmRequest = compactRecord({
    model: pickFirst(raw, ['model', 'provider_model']),
    messages: pickFirst(raw, ['messages_sent', 'messages']),
    payload: pickFirst(raw, ['structured_input', 'request_payload', 'payload']),
    params: pickFirst(raw, ['params', 'generation_params']),
    timeout_s: raw.timeout_s,
    max_retries: raw.max_retries,
  });
  if (llmRequest) artifacts.llmRequest = llmRequest;

  const llmRawResponse = pickFirst(raw, ['raw_response', 'response', 'content']);
  if (llmRawResponse !== undefined && event.category === 'llm') artifacts.llmRawResponse = llmRawResponse;

  const llmParsedResponse = pickFirst(raw, ['parsed_response', 'parsed', 'result']);
  if (llmParsedResponse !== undefined && event.category === 'llm') artifacts.llmParsedResponse = llmParsedResponse;

  const validation = compactRecord({
    status: pickFirst(raw, ['validation_status', 'status']),
    error: pickFirst(raw, ['validation_error', 'schema_error']),
    fallback_applied: raw.fallback_applied,
  });
  if (validation && event.category === 'llm') artifacts.validation = validation;

  if (event.category === 'budget') {
    // Extract budget fields directly from raw data
    const budgetData = {
      kind: pickFirst(raw, ['kind', 'reason', 'code', 'raw_type']),
      used: pickFirst(raw, ['consumed', 'used', 'steps_used']),
      limit: raw.limit,
      remaining: raw.remaining,
      max_steps: raw.max_steps,
      max_tool_calls_total: raw.max_tool_calls_total,
      max_wall_time_ms: raw.max_wall_time_ms,
      tool_timeout_ms: raw.tool_timeout_ms,
      max_retries: raw.max_retries,
    };
    // Keep all non-undefined values
    const filtered = Object.fromEntries(Object.entries(budgetData).filter(([, v]) => v !== undefined && v !== null));
    artifacts.budget = Object.keys(filtered).length > 0 ? filtered : raw;
  }

  if (event.category === 'planner' || event.category === 'decision' || event.category === 'policy' || event.category === 'retry') {
    artifacts.decision = compactRecord({
      kind: pickFirst(raw, ['kind', 'action_type', 'decision']),
      rationale: raw.rationale,
      agent_slug: raw.agent_slug,
      phase_id: raw.phase_id,
      question: raw.question,
      risk: raw.risk,
      requires_confirmation: raw.requires_confirmation,
      reason: raw.reason,
    }) ?? raw;
  }

  if (event.category === 'operation') {
    artifacts.operationInput = pickFirst(raw, ['arguments', 'parameters', 'input', 'payload']);
    artifacts.operationOutput = pickFirst(raw, ['result', 'output', 'data', 'observation']);
  }

  const errorContract = compactRecord({
    code: pickFirst(raw, ['runtime_error_code', 'code']),
    user_message: pickFirst(raw, ['runtime_error_message', 'user_message']),
    operator_message: pickFirst(raw, ['operator_message', 'error', 'message']),
    retryable: raw.retryable,
    recoverable: raw.recoverable,
    details: raw.details,
  });
  if (errorContract && (event.category === 'error' || event.status === 'error')) {
    artifacts.errorContract = errorContract;
  }

  return artifacts;
}
