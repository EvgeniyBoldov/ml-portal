/**
 * Tests for buildEntityTree
 */

import { describe, expect, it } from 'vitest';
import { buildEntityTree, findEntityById, flattenEntityTree, getEntityPath } from './buildEntityTree';
import type { SemanticEvent } from './types';

// Test data factories
function makeEvent(overrides: Partial<SemanticEvent> & { raw_type: string; id: string }): SemanticEvent {
  return {
    id: overrides.id,
    raw_type: overrides.raw_type,
    category: overrides.category ?? 'system',
    title: overrides.title ?? overrides.raw_type,
    summary: overrides.summary ?? '',
    status: overrides.status ?? 'info',
    phase: overrides.phase ?? 'system',
    iteration: overrides.iteration ?? 0,
    started_at: overrides.started_at ?? new Date().toISOString(),
    duration_ms: overrides.duration_ms ?? 100,
    inputs: overrides.inputs,
    outputs: overrides.outputs,
    decision: overrides.decision,
    budget: overrides.budget,
    refs: overrides.refs,
    raw: overrides.raw ?? {
      id: overrides.id,
      raw_type: overrides.raw_type,
      raw: {},
    },
  };
}

describe('buildEntityTree', () => {
  describe('simple run (user → llm → final)', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input', summary: 'Hello', inputs: { content: 'Hello' } }),
      makeEvent({ id: 'e2', raw_type: 'budget_policy', category: 'budget', budget: { max_steps: 10, max_tool_calls_total: 50 } }),
      makeEvent({ id: 'e3', raw_type: 'llm_request', category: 'llm', inputs: { model: 'gpt-4', messages: [{ role: 'user', content: 'Hello' }] } }),
      makeEvent({ id: 'e4', raw_type: 'llm_response', category: 'llm', status: 'ok', outputs: { content: 'Hi there!' } }),
      makeEvent({ id: 'e5', raw_type: 'final_response', category: 'final', status: 'ok', outputs: { content: 'Hi there!' } }),
    ];

    it('creates root run entity', () => {
      const tree = buildEntityTree(events);
      expect(tree.kind).toBe('run');
      expect(tree.children.length).toBeGreaterThan(0);
    });

    it('flattens to include all entities', () => {
      const tree = buildEntityTree(events);
      const flat = flattenEntityTree(tree);
      expect(flat.length).toBeGreaterThanOrEqual(3); // run + llm + final at least
    });

    it('finds entity by id', () => {
      const tree = buildEntityTree(events);
      const found = findEntityById(tree, tree.id);
      expect(found).toBeDefined();
    });

    it('returns entity path', () => {
      const tree = buildEntityTree(events);
      const llmEntities = flattenEntityTree(tree).filter(e => e.kind === 'llm');
      if (llmEntities.length > 0) {
        const path = getEntityPath(tree, llmEntities[0].id);
        expect(path.length).toBeGreaterThanOrEqual(2); // run -> llm
        expect(path[0].kind).toBe('run');
      }
    });
  });

  describe('run with tool call', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input', summary: 'Search docs' }),
      makeEvent({ id: 'e2', raw_type: 'planner_step', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'viewer' }, summary: 'call_agent: Need to search' }),
      makeEvent({ id: 'e3', raw_type: 'llm_request', category: 'llm', iteration: 1 }),
      makeEvent({ id: 'e4', raw_type: 'llm_response', category: 'llm', iteration: 1 }),
      makeEvent({
        id: 'e5',
        raw_type: 'operation_call',
        category: 'operation',
        raw: { id: 'e5', raw_type: 'operation_call', raw: { operation_slug: 'rag.search', call_id: 'c1', arguments: { query: 'test' } } },
      }),
      makeEvent({
        id: 'e6',
        raw_type: 'operation_result',
        category: 'operation',
        status: 'ok',
        raw: { id: 'e6', raw_type: 'operation_result', raw: { call_id: 'c1', success: true, result: { docs: [] } } },
      }),
      makeEvent({ id: 'e7', raw_type: 'final_response', category: 'final', status: 'ok' }),
    ];

    it('creates agent entity for planner_step call_agent', () => {
      const tree = buildEntityTree(events);
      const agents = flattenEntityTree(tree).filter(e => e.kind === 'agent');
      expect(agents.length).toBe(1);
      expect(agents[0].title).toContain('viewer');
    });

    it('creates tool entity for operation_call + operation_result', () => {
      const tree = buildEntityTree(events);
      const tools = flattenEntityTree(tree).filter(e => e.kind === 'tool');
      expect(tools.length).toBe(1);
      expect(tools[0].data.kind).toBe('tool');
      if (tools[0].data.kind === 'tool') {
        expect(tools[0].data.toolSlug).toBe('rag.search');
      }
    });

    it('nests tool under agent', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.kind === 'agent');
      expect(agent).toBeDefined();
      if (agent) {
        const hasToolChild = agent.children.some(c => c.kind === 'tool');
        expect(hasToolChild).toBe(true);
      }
    });
  });

  describe('run with retry', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input' }),
      makeEvent({
        id: 'e2',
        raw_type: 'operation_call',
        category: 'operation',
        raw: { id: 'e2', raw_type: 'operation_call', raw: { operation_slug: 'test.tool', call_id: 'c1' } },
      }),
      makeEvent({ id: 'e3', raw_type: 'protocol_retry', category: 'retry', decision: { reason: 'rate_limit' } }),
      makeEvent({
        id: 'e4',
        raw_type: 'operation_result',
        category: 'operation',
        status: 'ok',
        raw: { id: 'e4', raw_type: 'operation_result', raw: { call_id: 'c1', success: true } },
      }),
    ];

    it('captures retries in tool entity', () => {
      const tree = buildEntityTree(events);
      const tools = flattenEntityTree(tree).filter(e => e.kind === 'tool');
      expect(tools.length).toBe(1);
      if (tools[0].data.kind === 'tool') {
        expect(tools[0].data.retries).toBeDefined();
        expect(tools[0].data.retries?.length).toBe(1);
      }
    });
  });

  describe('run with error', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input' }),
      makeEvent({ id: 'e2', raw_type: 'planner_step', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'viewer' } }),
      makeEvent({ id: 'e3', raw_type: 'llm_request', category: 'llm' }),
      makeEvent({
        id: 'e4',
        raw_type: 'error',
        category: 'error',
        status: 'error',
        summary: 'LLM timeout',
        raw: { id: 'e4', raw_type: 'error', raw: { error_code: 'LLM_TIMEOUT', message: 'Request timed out' } },
      }),
    ];

    it('creates error entity', () => {
      const tree = buildEntityTree(events);
      const errors = flattenEntityTree(tree).filter(e => e.kind === 'error');
      expect(errors.length).toBe(1);
      expect(errors[0].status).toBe('error');
    });

    it('propagates error status to parent', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.kind === 'agent');
      expect(agent).toBeDefined();
      if (agent) {
        expect(['warn', 'error']).toContain(agent.status);
      }
    });
  });

  describe('run with multiple orchestrators (planner + fact_extractor)', () => {
    // This test represents future state when backend Stage 1 adds orchestrator events
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input' }),
      // Future: orchestrator_start for planner
      makeEvent({ id: 'e2', raw_type: 'orchestrator_start', category: 'system', raw: { id: 'e2', raw_type: 'orchestrator_start', raw: { slug: 'planner', role: 'planner' } } }),
      makeEvent({ id: 'e3', raw_type: 'planner_step', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'viewer' } }),
      makeEvent({ id: 'e4', raw_type: 'agent_start', category: 'system', raw: { id: 'e4', raw_type: 'agent_start', raw: { slug: 'viewer' } } }),
      makeEvent({ id: 'e5', raw_type: 'llm_request', category: 'llm' }),
      makeEvent({ id: 'e6', raw_type: 'llm_response', category: 'llm' }),
      makeEvent({ id: 'e7', raw_type: 'agent_end', category: 'system' }),
      // Future: orchestrator_end for planner
      makeEvent({ id: 'e8', raw_type: 'orchestrator_end', category: 'system' }),
      // Future: orchestrator_start for synthesizer
      makeEvent({ id: 'e9', raw_type: 'orchestrator_start', category: 'system', raw: { id: 'e9', raw_type: 'orchestrator_start', raw: { slug: 'synthesizer', role: 'synthesizer' } } }),
      makeEvent({ id: 'e10', raw_type: 'llm_request', category: 'llm' }),
      makeEvent({ id: 'e11', raw_type: 'llm_response', category: 'llm' }),
      makeEvent({ id: 'e12', raw_type: 'orchestrator_end', category: 'system' }),
      makeEvent({ id: 'e13', raw_type: 'final_response', category: 'final' }),
    ];

    it('creates orchestrator entities when backend Stage 1 events present', () => {
      const tree = buildEntityTree(events);
      const orchestrators = flattenEntityTree(tree).filter(e => e.kind === 'orchestrator');
      expect(orchestrators.length).toBe(2);
    });

    it('nests agent under orchestrator', () => {
      const tree = buildEntityTree(events);
      const orchestrator = flattenEntityTree(tree).find(e => e.kind === 'orchestrator' && e.title === 'planner');
      expect(orchestrator).toBeDefined();
      if (orchestrator) {
        const hasAgentChild = orchestrator.children.some(c => c.kind === 'agent');
        expect(hasAgentChild).toBe(true);
      }
    });
  });

  describe('unknown event handling', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input' }),
      makeEvent({ id: 'e2', raw_type: 'some_new_event_type_v2', category: 'system', title: 'New Event', summary: 'Unknown event' }),
    ];

    it('creates unknown entity for unclassified events', () => {
      const tree = buildEntityTree(events);
      const unknowns = flattenEntityTree(tree).filter(e => e.kind === 'unknown');
      expect(unknowns.length).toBe(1);
      expect(unknowns[0].status).toBe('warn');
      if (unknowns[0].data.kind === 'unknown') {
        expect(unknowns[0].data.rawType).toBe('some_new_event_type_v2');
      }
    });
  });

  describe('budget extraction', () => {
    const events: SemanticEvent[] = [
      makeEvent({
        id: 'e1',
        raw_type: 'budget_consumed',
        category: 'budget',
        budget: {
          consumed_planner_iterations: 2,
          max_planner_iterations: 10,
          consumed_tool_calls: 5,
          max_tool_calls_total: 50,
          remaining_wall_time_ms: 45000,
          max_wall_time_ms: 60000,
        },
      }),
    ];

    it('extracts budget metrics from budget events', () => {
      const tree = buildEntityTree(events);
      expect(tree.budgetSnapshot).toBeDefined();
      expect(tree.budgetSnapshot?.steps).toEqual({ used: 2, limit: 10 });
      expect(tree.budgetSnapshot?.tools).toEqual({ used: 5, limit: 50 });
    });
  });

  describe('LLM brief mode detection', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'llm_request', category: 'llm', inputs: { model: 'gpt-4' } }),
      makeEvent({
        id: 'e2',
        raw_type: 'llm_response',
        category: 'llm',
        status: 'ok',
        raw: {
          id: 'e2',
          raw_type: 'llm_response',
          raw: { messages_hash: 'abc123', system_prompt_hash: 'def456', content: 'Response' },
        },
      }),
    ];

    it('detects brief mode from hash fields', () => {
      const tree = buildEntityTree(events);
      const llms = flattenEntityTree(tree).filter(e => e.kind === 'llm');
      expect(llms.length).toBe(1);
      if (llms[0].data.kind === 'llm') {
        expect(llms[0].data.prompt?.isBriefMode).toBe(true);
        expect(llms[0].data.prompt?.messagesHash).toBe('abc123');
        expect(llms[0].data.prompt?.systemPromptHash).toBe('def456');
      }
    });
  });

  describe('sub-agent heuristic (MVP without backend Stage 1)', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input' }),
      makeEvent({ id: 'e2', raw_type: 'planner_step', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'sub-agent' } }),
      // In MVP, sub-agent llm/tool events are NOT visible (they're in separate run)
      // We only see operation_call/result through AgentExecutor translation
      makeEvent({
        id: 'e3',
        raw_type: 'operation_call',
        category: 'operation',
        raw: { id: 'e3', raw_type: 'operation_call', raw: { operation_slug: 'sub_agent_proxy', call_id: 'c1' } },
      }),
      makeEvent({
        id: 'e4',
        raw_type: 'operation_result',
        category: 'operation',
        status: 'ok',
        raw: { id: 'e4', raw_type: 'operation_result', raw: { call_id: 'c1', success: true, result: { summary: 'Sub-agent done' } } },
      }),
      makeEvent({ id: 'e5', raw_type: 'final_response', category: 'final' }),
    ];

    it('creates agent entity for sub-agent call (opaque block in MVP)', () => {
      const tree = buildEntityTree(events);
      const agents = flattenEntityTree(tree).filter(e => e.kind === 'agent');
      expect(agents.length).toBe(1);
      expect(agents[0].title).toContain('sub-agent');
    });

    it('shows sub-agent proxy as tool under agent', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.kind === 'agent');
      expect(agent).toBeDefined();
      if (agent) {
        const tools = agent.children.filter(c => c.kind === 'tool');
        expect(tools.length).toBe(1);
        if (tools[0].data.kind === 'tool') {
          expect(tools[0].data.toolSlug).toBe('sub_agent_proxy');
        }
      }
    });
  });
});
