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
      makeEvent({
        id: 'e2',
        raw_type: 'budget_snapshot',
        category: 'budget',
        budget: {
          owner_scope: 'run',
          owner_id: 'run-1',
          snapshot: {
            planner_iterations: { used: 0, limit: 10, remaining: 10 },
            tool_calls: { used: 0, limit: 50, remaining: 50 },
          },
        },
      }),
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
      makeEvent({ id: 'e2', raw_type: 'planner_decision', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'viewer' }, summary: 'call_agent: Need to search' }),
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

    it('creates agent entity for planner_decision call_agent', () => {
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
      makeEvent({ id: 'e2', raw_type: 'planner_decision', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'viewer' } }),
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

    it('aggregates scoped error into responsible entity data', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.kind === 'agent');
      expect(agent).toBeDefined();
      if (agent && 'errors' in agent.data) {
        const errors = (agent.data as { errors?: Array<{ code?: string }> }).errors ?? [];
        expect(errors).toHaveLength(1);
        expect(errors[0].code).toBe('LLM_TIMEOUT');
      }
    });
  });

  describe('tool failure debug payload', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'e1', raw_type: 'user_request', category: 'input' }),
      makeEvent({
        id: 'e2',
        raw_type: 'operation_call',
        category: 'operation',
        raw: { id: 'e2', raw_type: 'operation_call', raw: { operation_slug: 'collection.document.search', call_id: 'c1', arguments: { query: 'vpn' } } },
      }),
      makeEvent({
        id: 'e3',
        raw_type: 'operation_result',
        category: 'operation',
        status: 'error',
        raw: {
          id: 'e3',
          raw_type: 'operation_result',
          raw: {
            call_id: 'c1',
            success: false,
            user_message: 'Execution timed out after 30 seconds',
            operator_message: 'Execution timed out after 30 seconds',
            error_code: 'operation_timeout',
            source: 'tool',
            debug: {
              exception_type: 'TimeoutError',
              traceback: 'traceback text',
              context: { tool: 'collection.document.search' },
            },
          },
        },
      }),
    ];

    it('stores tool failure debug info in tool entity errors tab payload', () => {
      const tree = buildEntityTree(events);
      const tool = flattenEntityTree(tree).find(e => e.kind === 'tool');
      expect(tool).toBeDefined();
      if (tool?.data.kind === 'tool') {
        expect(tool.data.result?.debug?.exceptionType).toBe('TimeoutError');
        expect(tool.data.result?.debug?.stack).toBe('traceback text');
        expect(tool.data.errors?.[0]?.source).toBe('tool');
      }
    });
  });

  describe('3-pass: lifecycle events from Stage 1 backend', () => {
    // Full lifecycle event stream with entity_id / parent_entity_id
    const RUN_ID = 'run-abc';
    const ORCH_ID = 'run-abc:orchestrator';
    const ITER_ID = 'run-abc:planner:1';
    const AGENT_RUN_ID = 'run-abc:agent:viewer:1';
    const SYNTH_ID = 'run-abc:synthesis:1';
    const LLM_CALL_ID = 'llm-call-1';

    function lc(id: string, raw_type: string, raw: Record<string, unknown>): SemanticEvent {
      return makeEvent({ id, raw_type, category: 'system', raw: { id, raw_type, raw } });
    }

    const events: SemanticEvent[] = [
      lc('s1', 'run_start', { entity_id: RUN_ID, entity_type: 'run' }),
      lc('s2', 'orchestrator_start', { entity_id: ORCH_ID, entity_type: 'orchestrator', parent_entity_id: RUN_ID, parent_entity_type: 'run', role: 'planner' }),
      lc('s3', 'planner_iteration_start', { entity_id: ITER_ID, entity_type: 'planner_iteration', parent_entity_id: ORCH_ID, parent_entity_type: 'orchestrator', iteration: 1 }),
      makeEvent({ id: 'e4', raw_type: 'planner_decision', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'viewer' }, refs: { parent_entity_id: ITER_ID } }),
      lc('s5', 'agent_start', { entity_id: AGENT_RUN_ID, entity_type: 'agent_run', parent_entity_id: ITER_ID, parent_entity_type: 'planner_iteration', agent_slug: 'viewer' }),
      makeEvent({ id: 'e6', raw_type: 'llm_request', category: 'llm', refs: { parent_entity_id: AGENT_RUN_ID, llm_call_id: LLM_CALL_ID }, raw: { id: 'e6', raw_type: 'llm_request', raw: { llm_call_id: LLM_CALL_ID, parent_entity_id: AGENT_RUN_ID } } }),
      makeEvent({ id: 'e7', raw_type: 'llm_response', category: 'llm', status: 'ok', refs: { parent_entity_id: AGENT_RUN_ID, llm_call_id: LLM_CALL_ID }, raw: { id: 'e7', raw_type: 'llm_response', raw: { llm_call_id: LLM_CALL_ID, parent_entity_id: AGENT_RUN_ID } } }),
      makeEvent({ id: 'e8', raw_type: 'operation_call', category: 'operation', refs: { parent_entity_id: AGENT_RUN_ID }, raw: { id: 'e8', raw_type: 'operation_call', raw: { operation_slug: 'rag.search', call_id: 'c1', parent_entity_id: AGENT_RUN_ID } } }),
      makeEvent({ id: 'e9', raw_type: 'operation_result', category: 'operation', status: 'ok', refs: { parent_entity_id: AGENT_RUN_ID }, raw: { id: 'e9', raw_type: 'operation_result', raw: { call_id: 'c1', success: true, parent_entity_id: AGENT_RUN_ID } } }),
      makeEvent({
        id: 'e9a',
        raw_type: 'question_answer',
        category: 'system',
        summary: 'Какой регламент? → HR',
        refs: { parent_entity_id: ORCH_ID },
        raw: {
          id: 'e9a',
          raw_type: 'question_answer',
          raw: {
            entity_id: `${RUN_ID}:question-answer`,
            parent_entity_type: 'orchestrator',
            parent_entity_id: ORCH_ID,
            question_kind: 'clarify',
            question: 'Какой регламент?',
            user_answer: 'HR',
          },
        },
      }),
      lc('s10', 'agent_end', { entity_id: AGENT_RUN_ID, entity_type: 'agent_run', parent_entity_id: ITER_ID, parent_entity_type: 'planner_iteration', agent_slug: 'viewer', status: 'completed' }),
      lc('s11', 'planner_iteration_end', { entity_id: ITER_ID, entity_type: 'planner_iteration', parent_entity_id: ORCH_ID, iteration: 1, status: 'completed' }),
      lc('s12', 'orchestrator_end', { entity_id: ORCH_ID, entity_type: 'orchestrator', parent_entity_id: RUN_ID, status: 'completed' }),
      lc('s13', 'synthesis_start', { entity_id: SYNTH_ID, entity_type: 'synthesis_run', parent_entity_id: RUN_ID, parent_entity_type: 'run' }),
      makeEvent({ id: 'e14', raw_type: 'final_response', category: 'final', status: 'ok', refs: { parent_entity_id: SYNTH_ID }, outputs: { content: 'Done' } }),
      lc('s15', 'synthesis_end', { entity_id: SYNTH_ID, entity_type: 'synthesis_run', parent_entity_id: RUN_ID, status: 'completed' }),
      lc('s16', 'run_end', { entity_id: RUN_ID, entity_type: 'run', status: 'completed' }),
    ];

    it('creates run entity at root', () => {
      const tree = buildEntityTree(events);
      expect(tree.kind).toBe('run');
      expect(tree.id).toBe(RUN_ID);
    });

    it('creates orchestrator inside active phase', () => {
      const tree = buildEntityTree(events);
      const activePhase = tree.children.find(
        (e) => e.kind === 'phase' && e.data.kind === 'phase' && e.data.phaseRole === 'active',
      );
      expect(activePhase).toBeDefined();
      const orch = flattenEntityTree(tree).find(e => e.id === ORCH_ID);
      expect(orch).toBeDefined();
      expect(orch?.kind).toBe('orchestrator');
      expect(orch?.parentId).toBe(activePhase?.id);
    });

    it('creates planner iteration as child of orchestrator', () => {
      const tree = buildEntityTree(events);
      const iter = flattenEntityTree(tree).find(e => e.id === ITER_ID);
      expect(iter).toBeDefined();
      expect(iter?.kind).toBe('planner');
      expect(iter?.parentId).toBe(ORCH_ID);
    });

    it('creates agent as child of planner iteration', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.id === AGENT_RUN_ID);
      expect(agent).toBeDefined();
      expect(agent?.kind).toBe('agent');
      expect(agent?.parentId).toBe(ITER_ID);
      expect(agent?.data.kind === 'agent' && agent.data.slug).toBe('viewer');
    });

    it('attaches llm entity under agent via parent_entity_id', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.id === AGENT_RUN_ID);
      expect(agent).toBeDefined();
      const llmChildren = agent!.children.filter(c => c.kind === 'llm');
      expect(llmChildren.length).toBe(1);
    });

    it('attaches tool entity under agent via parent_entity_id', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.id === AGENT_RUN_ID);
      expect(agent).toBeDefined();
      const toolChildren = agent!.children.filter(c => c.kind === 'tool');
      expect(toolChildren.length).toBe(1);
    });

    it('creates interaction step under orchestrator for question-answer', () => {
      const tree = buildEntityTree(events);
      const interaction = flattenEntityTree(tree).find(e => e.kind === 'interaction');
      expect(interaction).toBeDefined();
      expect(interaction?.parentId).toBe(ORCH_ID);
      if (interaction?.data.kind === 'interaction') {
        expect(interaction.data.question).toBe('Какой регламент?');
        expect(interaction.data.answer).toBe('HR');
      }
    });

    it('creates synthesis entity inside active phase', () => {
      const tree = buildEntityTree(events);
      const activePhase = tree.children.find(
        (e) => e.kind === 'phase' && e.data.kind === 'phase' && e.data.phaseRole === 'active',
      );
      expect(activePhase).toBeDefined();
      const synth = flattenEntityTree(tree).find(e => e.id === SYNTH_ID);
      expect(synth).toBeDefined();
      expect(synth?.kind).toBe('orchestrator');
      expect(synth?.parentId).toBe(activePhase?.id);
    });

    it('sets completed status on entities after *_end events', () => {
      const tree = buildEntityTree(events);
      const agent = flattenEntityTree(tree).find(e => e.id === AGENT_RUN_ID);
      expect(agent?.status).toBe('ok');
    });

    it('planner_decision enriches planner iteration title', () => {
      const tree = buildEntityTree(events);
      const iter = flattenEntityTree(tree).find(e => e.id === ITER_ID);
      expect(iter).toBeDefined();
      // planner_decision was attached to iter, so its stepKind is updated
      expect(iter?.data.kind).toBe('planner');
    });

    it('tree depth is correct: run(0) → phase(1) → orch(2) → iter(3) → agent(4) → tool(5)', () => {
      const tree = buildEntityTree(events);
      expect(tree.depth).toBe(0);
      const activePhase = tree.children.find(
        (e) => e.kind === 'phase' && e.data.kind === 'phase' && e.data.phaseRole === 'active',
      );
      expect(activePhase?.depth).toBe(1);
      const orch = flattenEntityTree(tree).find(e => e.id === ORCH_ID);
      expect(orch?.depth).toBe(2);
      const iter = flattenEntityTree(tree).find(e => e.id === ITER_ID);
      expect(iter?.depth).toBe(3);
      const agent = flattenEntityTree(tree).find(e => e.id === AGENT_RUN_ID);
      expect(agent?.depth).toBe(4);
      const tool = agent!.children.find(c => c.kind === 'tool');
      expect(tool?.depth).toBe(5);
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

  describe('interaction request handling', () => {
    const events: SemanticEvent[] = [
      makeEvent({ id: 'run-start', raw_type: 'run_start', category: 'system', raw: { id: 'run-start', raw_type: 'run_start', raw: { entity_id: 'run-1', entity_type: 'run' } } }),
      makeEvent({
        id: 'wait-1',
        raw_type: 'waiting_input',
        category: 'system',
        title: 'Запрос уточнения',
        summary: 'Укажите VLAN',
        raw: {
          id: 'wait-1',
          raw_type: 'waiting_input',
          raw: {
            question: 'Укажите VLAN',
            reason: 'waiting_input',
            parent_entity_id: 'run-1',
          },
        },
        refs: { parent_entity_id: 'run-1' },
      }),
    ];

    it('keeps waiting_input as an interaction entity instead of runtime noise', () => {
      const tree = buildEntityTree(events);
      const interaction = flattenEntityTree(tree).find((entity) => entity.kind === 'interaction');
      expect(interaction).toBeDefined();
      expect(interaction?.parentId).toBeTruthy();
      const parent = interaction?.parentId ? findEntityById(tree, interaction.parentId) : undefined;
      expect(parent).toBeDefined();
      expect(parent?.kind === 'run' || parent?.kind === 'phase').toBe(true);
      if (interaction?.data.kind === 'interaction') {
        expect(interaction.data.interactionKind).toBe('clarify');
        expect(interaction.data.question).toBe('Укажите VLAN');
      }
    });
  });

  describe('clarify dialog grouping', () => {
    const RUN_ID = 'run-clarify';
    const ORCH_ID = `${RUN_ID}:orchestrator`;
    const ITER_ID = `${RUN_ID}:planner:1`;
    const QUESTION = 'Пожалуйста, уточните, что именно нужно проверить?';

    const events: SemanticEvent[] = [
      makeEvent({
        id: RUN_ID,
        raw_type: 'run_start',
        category: 'system',
        raw: { id: RUN_ID, raw_type: 'run_start', raw: { entity_id: RUN_ID, entity_type: 'run' } },
      }),
      makeEvent({
        id: `${RUN_ID}:orch-start`,
        raw_type: 'orchestrator_start',
        category: 'system',
        raw: {
          id: `${RUN_ID}:orch-start`,
          raw_type: 'orchestrator_start',
          raw: {
            entity_id: ORCH_ID,
            parent_entity_id: RUN_ID,
            slug: 'orchestrator',
            role: 'planner',
          },
        },
      }),
      makeEvent({
        id: `${RUN_ID}:iter-start`,
        raw_type: 'planner_iteration_start',
        category: 'system',
        raw: {
          id: `${RUN_ID}:iter-start`,
          raw_type: 'planner_iteration_start',
          raw: {
            entity_id: ITER_ID,
            parent_entity_id: ORCH_ID,
          },
        },
      }),
      makeEvent({
        id: `${RUN_ID}:llm-clarify`,
        raw_type: 'llm_turn',
        category: 'llm',
        raw: {
          id: `${RUN_ID}:llm-clarify`,
          raw_type: 'llm_turn',
          raw: {
            parent_entity_id: ITER_ID,
            content: JSON.stringify({ kind: 'clarify', question: QUESTION }),
          },
        },
        refs: { parent_entity_id: ITER_ID },
      }),
      makeEvent({
        id: `${RUN_ID}:decision`,
        raw_type: 'planner_decision',
        category: 'planner',
        raw: {
          id: `${RUN_ID}:decision`,
          raw_type: 'planner_decision',
          raw: {
            parent_entity_id: ITER_ID,
            kind: 'clarify',
            rationale: 'Need clarification',
          },
        },
        decision: { kind: 'clarify', rationale: 'Need clarification' },
      }),
      makeEvent({
        id: `${RUN_ID}:qa`,
        raw_type: 'question_answer',
        category: 'system',
        raw: {
          id: `${RUN_ID}:qa`,
          raw_type: 'question_answer',
          raw: {
            entity_id: `${RUN_ID}:question-answer`,
            parent_entity_id: ORCH_ID,
            question: QUESTION,
            user_answer: 'уточнил',
            question_kind: 'clarify',
            resume_action: 'input',
            source_run_id: RUN_ID,
          },
        },
        refs: { parent_entity_id: ORCH_ID },
      }),
      makeEvent({
        id: `${RUN_ID}:iter-end`,
        raw_type: 'planner_iteration_end',
        category: 'system',
        raw: {
          id: `${RUN_ID}:iter-end`,
          raw_type: 'planner_iteration_end',
          raw: {
            entity_id: ITER_ID,
            parent_entity_id: ORCH_ID,
            status: 'paused',
          },
        },
      }),
      makeEvent({
        id: `${RUN_ID}:orch-end`,
        raw_type: 'orchestrator_end',
        category: 'system',
        raw: {
          id: `${RUN_ID}:orch-end`,
          raw_type: 'orchestrator_end',
          raw: {
            entity_id: ORCH_ID,
            parent_entity_id: RUN_ID,
            status: 'waiting_input',
          },
        },
      }),
    ];

    it('groups clarify llm and answer into a dialog container', () => {
      const tree = buildEntityTree(events);
      const dialog = flattenEntityTree(tree).find((entity) => entity.kind === 'dialog');
      expect(dialog).toBeDefined();
      expect(dialog?.parentId).toBe(ITER_ID);
      if (dialog?.data.kind === 'dialog') {
        expect(dialog.data.interactionKind).toBe('clarify');
        expect(dialog.data.items?.length).toBe(1);
        expect(dialog.data.items?.[0]?.question).toBe(QUESTION);
        expect(dialog.data.items?.[0]?.answer).toBe('уточнил');
      }
      const llm = dialog?.children.find((child) => child.kind === 'llm');
      const interaction = dialog?.children.find((child) => child.kind === 'interaction');
      expect(llm).toBeDefined();
      expect(interaction).toBeDefined();
      expect(interaction?.parentId).toBe(dialog?.id);
    });
  });

  describe('budget extraction', () => {
    const events: SemanticEvent[] = [
      makeEvent({
        id: 'e1',
        raw_type: 'budget_snapshot',
        category: 'budget',
        budget: {
          owner_scope: 'run',
          owner_id: 'run-1',
          snapshot: {
            planner_iterations: { used: 2, limit: 10, remaining: 8 },
            tool_calls: { used: 5, limit: 50, remaining: 45 },
            wall_time_ms: { used: 15000, limit: 60000, remaining: 45000 },
          },
        },
      }),
    ];

    it('extracts budget metrics from budget events', () => {
      const tree = buildEntityTree(events);
      expect(tree.budgetSnapshot).toBeDefined();
      expect(tree.budgetSnapshot?.steps).toEqual({ used: 2, limit: 10, remaining: 8 });
      expect(tree.budgetSnapshot?.tools).toEqual({ used: 5, limit: 50, remaining: 45 });
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
      makeEvent({ id: 'e2', raw_type: 'planner_decision', category: 'planner', decision: { kind: 'call_agent', agent_slug: 'sub-agent' } }),
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
