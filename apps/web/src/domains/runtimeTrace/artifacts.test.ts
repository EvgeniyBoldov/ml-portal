import { describe, expect, it } from 'vitest';
import { extractTraceArtifacts } from './artifacts';
import type { SemanticEvent } from './types';

function baseEvent(partial: Partial<SemanticEvent>): SemanticEvent {
  return {
    id: partial.id ?? 'e1',
    raw_type: partial.raw_type ?? 'llm_response',
    category: partial.category ?? 'llm',
    title: partial.title ?? 'LLM ответ',
    summary: partial.summary ?? '',
    status: partial.status ?? 'info',
    phase: partial.phase ?? 'llm',
    iteration: partial.iteration ?? 0,
    inputs: partial.inputs,
    outputs: partial.outputs,
    decision: partial.decision,
    budget: partial.budget,
    refs: partial.refs,
    raw: partial.raw ?? { id: 'e1', raw_type: 'llm_response', raw: {} },
  };
}

describe('runtimeTrace artifacts', () => {
  it('extracts llm artifacts from raw payload', () => {
    const event = baseEvent({
      raw_type: 'llm_response',
      category: 'llm',
      raw: {
        id: 'e1',
        raw_type: 'llm_response',
        raw: {
          system_prompt: 'You are planner',
          model: 'gpt-x',
          messages_sent: [{ role: 'user', content: '{}' }],
          structured_input: { goal: 'find docs' },
          raw_response: '{"kind":"final"}',
          parsed_response: { kind: 'final' },
          validation_status: 'success',
        },
      },
    });

    const artifacts = extractTraceArtifacts(event);
    expect(artifacts.prompt).toBe('You are planner');
    expect(artifacts.llmRequest).toEqual({
      model: 'gpt-x',
      messages: [{ role: 'user', content: '{}' }],
      payload: { goal: 'find docs' },
    });
    expect(artifacts.llmRawResponse).toBe('{"kind":"final"}');
    expect(artifacts.llmParsedResponse).toEqual({ kind: 'final' });
    expect(artifacts.validation).toEqual({ status: 'success' });
  });

  it('extracts budget and decision artifacts', () => {
    const budgetEvent = baseEvent({
      raw_type: 'budget_snapshot',
      category: 'budget',
      raw: {
        id: 'b1',
        raw_type: 'budget_snapshot',
        raw: {
          owner_scope: 'run',
          owner_id: 'run-1',
          snapshot: { agent_steps: { used: 10, limit: 10, remaining: 0 } },
          delta: { agent_steps: 1 },
          reason: 'limit_exceeded',
          at_ms: 1000,
        },
      },
    });
    const decisionEvent = baseEvent({
      raw_type: 'planner_decision',
      category: 'planner',
      raw: {
        id: 'd1',
        raw_type: 'planner_decision',
        raw: { kind: 'call_agent', rationale: 'need infra data', agent_slug: 'netops' },
      },
    });

    expect(extractTraceArtifacts(budgetEvent).budget).toEqual({
      owner_scope: 'run',
      owner_id: 'run-1',
      snapshot: { agent_steps: { used: 10, limit: 10, remaining: 0 } },
      delta: { agent_steps: 1 },
      reason: 'limit_exceeded',
      at_ms: 1000,
    });
    expect(extractTraceArtifacts(decisionEvent).decision).toEqual({
      kind: 'call_agent',
      rationale: 'need infra data',
      agent_slug: 'netops',
    });
  });

  it('extracts error contract for runtime errors', () => {
    const event = baseEvent({
      raw_type: 'error',
      category: 'error',
      status: 'error',
      raw: {
        id: 'err1',
        raw_type: 'error',
        raw: {
          runtime_error_code: 'budget_exceeded',
          runtime_error_message: 'Лимит исчерпан',
          operator_message: 'planner max steps reached',
          retryable: false,
        },
      },
    });
    expect(extractTraceArtifacts(event).errorContract).toEqual({
      code: 'budget_exceeded',
      user_message: 'Лимит исчерпан',
      operator_message: 'planner max steps reached',
      retryable: false,
    });
  });
});
