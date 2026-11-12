import { describe, expect, it } from 'vitest';

import { memoryContextFromPayload, memoryContextFromTool, projectTraceRun, projectTraceStages, resolveTraceInspectionTarget, stepFor, type TraceExecutorRun } from './traceProjection';
import { replayRuntimeJournal, type RuntimeJournalEvent } from './traceState';

const event = (sequence: number, eventType: string, payload: Record<string, unknown>): RuntimeJournalEvent => ({
  id: `event-${sequence}`,
  run_id: 'run-1',
  sequence,
  event_type: eventType,
  occurred_at: '2026-08-21T08:55:00.000Z',
  entity_type: typeof payload.entity_type === 'string' ? payload.entity_type : null,
  entity_id: typeof payload.entity_id === 'string' ? payload.entity_id : null,
  parent_entity_type: typeof payload.parent_entity_type === 'string' ? payload.parent_entity_type : null,
  parent_entity_id: typeof payload.parent_entity_id === 'string' ? payload.parent_entity_id : null,
  caused_by_event_id: null,
  duration_ms: null,
  payload,
});

function projectAgentExecutor(
  endPayload: Record<string, unknown>,
  precedingEvents: RuntimeJournalEvent[] = [],
): TraceExecutorRun {
  const base = [
    event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
    event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
    event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
  ];
  const terminalSequence = 4 + precedingEvents.length;
  const state = replayRuntimeJournal([
    ...base,
    ...precedingEvents,
    event(terminalSequence, 'agent_end', {
      entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1',
      status: 'completed', ...endPayload,
    }),
  ]);
  return projectTraceStages(state)[0].steps[0].executorRuns[0];
}

describe('projectTraceStages memory components', () => {
  it('links complete tool rows from the next LLM request only for the same owner and call', () => {
    const payload = JSON.stringify({ status: 'ready', result_id: 'result-1', revision: 2, records: [{ name: 'verified' }], source_coverage: { complete: true } });
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'result.sql', call_id: 'tool-1' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', call_id: 'tool-1', success: true, result_delivery: 'stored', result_id: 'result-1', result_inline_complete: true, data: { row_count: 1, payload_type: 'array' } }),
      event(6, 'llm_request', { entity_type: 'llm_call', entity_id: 'wrong-owner', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-2', messages: [{ role: 'tool', tool_call_id: 'tool-1', content: JSON.stringify({ rows: [{ name: 'wrong' }], _runtime_result: { delivery: 'inline', inline_complete: true } }) }] }),
      event(7, 'llm_request', { entity_type: 'llm_call', entity_id: 'next', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', messages: [{ role: 'tool', tool_call_id: 'tool-1', content: payload }] }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'tool_call:tool-1');
    expect(target?.kind === 'call' && target.call.responseView?.toolResult).toMatchObject({
      inlineDataAvailable: true, inlineData: [{ name: 'verified' }],
    });
  });

  it.each([[], 0, false, null, 'value'])('preserves model receipt records value %j, including empty/falsy values', (records) => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iter-a' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-a', parent_entity_type: 'planner_iteration', parent_entity_id: 'iter-a' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-a', parent_entity_type: 'step', parent_entity_id: 'step-a' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'call-a', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-a', call_id: 'call-a', tool: 'result.read' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'call-a', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-a', call_id: 'call-a', success: true, result_delivery: 'stored', result_id: 'result-a', result_inline_complete: false, data: { result_id: 'result-a', payload_type: 'array', row_count: 1 } }),
      event(6, 'status', { stage: 'tool_result_batch_projected', entity_type: 'agent_execution', entity_id: 'agent-a', parent_entity_type: 'step', parent_entity_id: 'step-a', call_ids: ['call-a'], inline_complete: [true] }),
      event(7, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-a', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-a', messages: [{ role: 'tool', tool_call_id: 'call-a', content: JSON.stringify({ status: 'ready', result_id: 'result-a', revision: 1, records }) }] }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'tool_call:call-a');
    expect(target?.kind === 'call' && target.call.responseView?.toolResult).toMatchObject({
      inlineComplete: true, inlineDataAvailable: true, inlineData: records,
    });
  });

  it('reads text protocol tool_result blocks and lets final batch coverage downgrade preliminary inline metadata', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iter-text' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-text', parent_entity_type: 'planner_iteration', parent_entity_id: 'iter-text' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-text', parent_entity_type: 'step', parent_entity_id: 'step-text' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'call-text', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-text', call_id: 'call-text', tool: 'search' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'call-text', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-text', call_id: 'call-text', success: true, result_inline_complete: true, data: [{ name: 'preview' }] }),
      event(6, 'status', { stage: 'tool_result_batch_projected', entity_type: 'agent_execution', entity_id: 'agent-text', parent_entity_type: 'step', parent_entity_id: 'step-text', call_ids: ['other', 'call-text'], inline_complete: [true, false], omitted_call_ids: ['call-text'], direct_recoveries: { 'call-text': { result_id: 'recovered', revision: 3, reason: 'batch_context_budget' } } }),
      event(7, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-text', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-text', messages: [{ role: 'user', content: 'prior result\n```tool_result\n{"call_id":"call-text","result":{"status":"ready","result_id":"r","revision":1,"records":[{"id":1}],"warnings":["partial"]}}\n```' }] }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'tool_call:call-text');
    expect(target?.kind === 'call' && target.call.responseView?.toolResult).toMatchObject({
      inlineComplete: false, preparedInlineComplete: false,
      inlineDataAvailable: true, inlineData: [{ id: 1 }],
      inlineDataContext: { status: 'ready', revision: 1, warnings: ['partial'] },
      directRecovery: { resultId: 'recovered', revision: 3 },
    });
    expect(target?.kind === 'call' && target.call.responseView?.toolResult?.data).toBeUndefined();
  });

  it('does not claim model delivery from execution result or a batch without a later matching request', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iter-lone' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-lone', parent_entity_type: 'planner_iteration', parent_entity_id: 'iter-lone' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-lone', parent_entity_type: 'step', parent_entity_id: 'step-lone' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'call-lone', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-lone', call_id: 'call-lone', tool: 'search' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'call-lone', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-lone', call_id: 'call-lone', success: true, result_inline_complete: true, data: [{ id: 1 }] }),
      event(6, 'status', { stage: 'tool_result_batch_projected', entity_type: 'agent_execution', entity_id: 'agent-lone', parent_entity_type: 'step', parent_entity_id: 'step-lone', call_ids: ['call-lone'], inline_complete: [true] }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'tool_call:call-lone');
    expect(target?.kind === 'call' && target.call.responseView?.toolResult).toMatchObject({ preparedInlineComplete: true });
    expect(target?.kind === 'call' && target.call.responseView?.toolResult?.inlineComplete).toBeUndefined();
    expect(target?.kind === 'call' && target.call.responseView?.toolResult?.inlineDataAvailable).toBeUndefined();
  });

  it('does not interpret a stored pointer or sample as a complete model response', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'search', call_id: 'tool-1' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', call_id: 'tool-1', success: true, result_delivery: 'stored', result_id: 'result-1', result_inline_complete: false, data: { row_count: 50, payload_type: 'array' } }),
      event(6, 'llm_request', { entity_type: 'llm_call', entity_id: 'next', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', messages: [{ role: 'tool', tool_call_id: 'tool-1', content: JSON.stringify({ sample: [{ name: 'example' }], _runtime_result: { delivery: 'stored', inline_complete: false } }) }] }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'tool_call:tool-1');
    expect(target?.kind === 'call' && target.call.responseView?.toolResult?.inlineDataAvailable).toBeUndefined();
  });
  it('shows the root route policy as its own trace stage with matched conditions', () => {
    const state = replayRuntimeJournal([
      event(1, 'route_policy_start', {
        entity_type: 'route_policy', entity_id: 'route-policy-1', parent_entity_type: 'run', parent_entity_id: 'run-1',
        user_request: 'посмотри в инвентори какие у меня есть коммутаторы',
      }),
      event(2, 'route_policy_decision', {
        entity_type: 'route_policy', entity_id: 'route-policy-1', parent_entity_type: 'run', parent_entity_id: 'run-1',
        route: 'planner', matched: true, rule_id: 'live_netbox_inventory_lookup',
        detail: 'Запрошены актуальные записи NetBox, агент доступен.',
        signals: ['inventory_source_mentioned', 'current_records_requested', 'inventory_agent_available'],
        source_agent: 'inventory.netbox',
      }),
      event(3, 'route_policy_end', {
        entity_type: 'route_policy', entity_id: 'route-policy-1', parent_entity_type: 'run', parent_entity_id: 'run-1', status: 'completed',
      }),
    ]);

    const stage = projectTraceStages(state)[0];
    expect(stage.kind).toBe('route_policy');
    expect(stage.routePolicy).toMatchObject({
      route: 'planner', matched: true, ruleId: 'live_netbox_inventory_lookup',
      sourceAgent: 'inventory.netbox', userRequest: 'посмотри в инвентори какие у меня есть коммутаторы',
    });
    const policyExecutor = stage.executorRuns[0];
    expect(policyExecutor).toMatchObject({ executorName: 'Рекомендация маршрута', kind: 'route_policy' });
    expect(resolveTraceInspectionTarget(state, policyExecutor.inspectorKey)?.tabs.map((item) => item.id)).toEqual(['info', 'route_policy', 'raw']);
  });

  it('projects only persisted fact changes for the fact compactor inspector', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'memory-1', role: 'memory' }),
      event(2, 'agent_start', { entity_type: 'agent_execution', entity_id: 'compactor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1', agent_slug: 'fact_compactor' }),
      event(3, 'memory_component_result', {
        entity_type: 'agent_execution', entity_id: 'compactor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1',
        component_name: 'fact_compactor', status: 'ok', inserted_count: 1, updated_count: 0, skipped_count: 0,
        facts: [{ scope: 'tenant', kind: 'fact', subject: 'network.zone', value: 'production', change_type: 'candidate_confirmed', status_before: 'pending', status_after: 'confirmed', support_before: 2, support_after: 3, support_delta: 1, compaction_action: 'merge' }],
      }),
      event(4, 'agent_end', { entity_type: 'agent_execution', entity_id: 'compactor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1', status: 'completed' }),
    ]);

    const compactor = projectTraceStages(state)[0].executorRuns[0];
    const target = resolveTraceInspectionTarget(state, compactor.inspectorKey);
    expect(compactor.kind).toBe('fact_compactor');
    expect(target?.kind).toBe('executor');
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Задача', 'Решения', 'RAW']);
    expect(compactor.memoryResult?.facts).toEqual([expect.objectContaining({
      subject: 'network.zone',
      changeType: 'candidate_confirmed',
      statusBefore: 'pending',
      statusAfter: 'confirmed',
      supportDelta: 1,
    })]);
  });

  it('projects typed candidate decisions from canonical status events', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'memory-1', role: 'memory' }),
      event(2, 'agent_start', { entity_type: 'agent_execution', entity_id: 'extractor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1', agent_slug: 'fact_extractor' }),
      event(3, 'status', {
        stage: 'memory_candidate_decision', entity_type: 'agent_execution', entity_id: 'extractor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1',
        component_name: 'fact_extractor', decision_phase: 'extraction_validation', outcome: 'rejected', reason_code: 'below_confidence', candidate_ids: ['extractor:1'],
        candidate: { scope: 'user', kind: 'fact', subject: 'language', value: 'Russian', confidence: 0.2 }, evidence: { count: 1, refs: [{ source_type: 'user_message', source_ref: 'turn-1' }] },
      }),
      event(4, 'status', {
        stage: 'memory_component_result', entity_type: 'agent_execution', entity_id: 'extractor-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-1',
        component_name: 'fact_extractor', status: 'ok', inserted_count: 0, updated_count: 0, skipped_count: 1, facts: [],
      }),
    ]);

    const extractor = projectTraceStages(state)[0].executorRuns[0];
    expect(extractor.memoryResult?.decisions).toEqual([expect.objectContaining({
      outcome: 'rejected', reasonCode: 'below_confidence', evidenceCount: 1,
      fact: expect.objectContaining({ subject: 'language' }),
    })]);
  });

  it('projects preflight and the effective system prompt onto the owning executor', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'preflight_started', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1' }),
      event(5, 'preflight_completed', {
        entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', mode: 'partial', duration_ms: 12,
        missing: { tools: [], collections: ['private_docs (rbac_denied)'], credentials: ['dcbox'] }, operations_count: 4, data_instances_count: 2,
      }),
      event(6, 'llm_request', {
        entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1',
        messages: [{ role: 'system', content: 'System prompt' }],
      }),
    ]);

    const executor = projectTraceStages(state)[0].steps[0].executorRuns[0];
    expect(executor.prompt?.text).toBe('System prompt');
    const inspection = resolveTraceInspectionTarget(state, executor.inspectorKey);
    expect(inspection?.tabs.map((item) => item.id)).not.toContain('validation');
    expect(executor.preflight).toMatchObject({
      mode: 'partial', durationMs: 12, operationsCount: 4, dataInstancesCount: 2,
      missing: { tools: [], collections: ['private_docs (rbac_denied)'], credentials: ['dcbox'] },
    });
  });

  it('projects the turn preflight route contract into the route inspector tab', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'preflight-1', role: 'turn_preflight' }),
      event(2, 'llm_request', {
        entity_type: 'llm_call', entity_id: 'call-1', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-1',
        messages: [{ role: 'user', content: JSON.stringify({ user_request: 'Запомни факт', mechanical_lookup: { entities: ['НОП'] } }) }],
      }),
      event(3, 'llm_response', {
        entity_type: 'llm_call', entity_id: 'call-1', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-1',
        content: JSON.stringify({ route: 'planner', task_brief: {
          goal: 'Сохранить факт', direction: 'В память пользователя', expected_result: 'Факт сохранён',
          entity_hints: ['НОП'], project_hints: [], constraints: ['не выдумывать'],
        } }),
      }),
      event(4, 'preflight_route_decision', {
        entity_type: 'orchestrator', entity_id: 'preflight-1', parent_entity_type: 'run', parent_entity_id: 'run-1',
        proposed_route: 'planner', effective_route: 'tool_call', reason: 'runtime_reroute', detail: 'В текущем состоянии нужен операционный источник.',
      }),
      event(5, 'access_snapshot', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-1', items: [{ kind: 'tool', key: 'memory.search', label: 'Поиск в памяти', status: 'available' }] }),
      event(6, 'orchestrator_end', { entity_type: 'orchestrator', entity_id: 'preflight-1', role: 'turn_preflight', status: 'planner' }),
    ]);

    const executor = projectTraceStages(state).find((stage) => stage.kind === 'turn_preflight')?.executorRuns[0];
    expect(executor?.route).toEqual(expect.objectContaining({
      proposed: 'planner', effective: 'tool_call', reason: 'runtime_reroute', detail: 'В текущем состоянии нужен операционный источник.', goal: 'Сохранить факт', direction: 'В память пользователя', expectedResult: 'Факт сохранён',
      entityHints: ['НОП'], constraints: ['не выдумывать'],
      input: { user_request: 'Запомни факт', mechanical_lookup: { entities: ['НОП'] } },
    }));
    expect(executor?.accessSnapshot?.items).toContainEqual(expect.objectContaining({ key: 'memory.search', status: 'available' }));
  });

  it.each([undefined, true, false])('shows preflight memory.search while waiting and after result=%s', (success) => {
    const events = [
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'preflight-search', role: 'turn_preflight' }),
      event(2, 'llm_request', { entity_type: 'llm_call', entity_id: 'route-search', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-search' }),
      event(3, 'llm_response', { entity_type: 'llm_call', entity_id: 'route-search', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-search', content: JSON.stringify({ route: 'tool_call', tool_call: { operation: 'memory.search', arguments: { query: 'NIMS' } } }) }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'search-call', call_id: 'search-call', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-search', tool: 'memory.search', arguments: { query: 'NIMS' } }),
    ];
    if (success !== undefined) events.push(event(5, 'tool_result', {
      entity_type: 'tool_call', entity_id: 'search-call', call_id: 'search-call', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-search', tool: 'memory.search', success, data: { items: [] },
    }));
    const state = replayRuntimeJournal(events);
    const executor = projectTraceStages(state).find((stage) => stage.kind === 'turn_preflight')?.executorRuns[0];
    expect(executor?.calls.map((call) => call.kind)).toEqual(['llm', 'tool']);
    const search = executor?.calls[1];
    expect(search?.requestView.toolName).toBe('memory.search');
    expect(search?.entity.status).toBe(success === undefined ? 'running' : success ? 'completed' : 'failed');
    expect(resolveTraceInspectionTarget(state, 'tool_call:search-call')?.kind).toBe('call');
  });

  it('does not throw when turn preflight has an empty LLM response', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'preflight-empty', role: 'turn_preflight' }),
      event(2, 'llm_request', { entity_type: 'llm_call', entity_id: 'call-empty', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-empty' }),
      event(3, 'llm_response', { entity_type: 'llm_call', entity_id: 'call-empty', parent_entity_type: 'orchestrator', parent_entity_id: 'preflight-empty' }),
    ]);

    expect(() => projectTraceStages(state)).not.toThrow();
  });

  it('keeps a planner proposal scoped to its iteration and maps planned tasks to steps', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', iteration_number: 1 }),
      event(2, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', purpose: 'planning_decision' }),
      event(3, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', purpose: 'planning_decision', terminal: true }),
      event(4, 'plan_iteration_applied', {
        entity_type: 'plan', entity_id: 'plan-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', iteration_id: 'iteration-1',
        proposal: { terminal: 'planner', tasks: [{ task_id: 'plan-1', executor: 'tech_fact_manager', intent: 'search_fact', instructions: 'Найти определение' }] },
      }),
      event(5, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-2', iteration_number: 2 }),
      event(6, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', purpose: 'planning_decision' }),
      event(7, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', purpose: 'planning_decision', terminal: true }),
      event(8, 'plan_iteration_applied', {
        entity_type: 'plan', entity_id: 'plan-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', iteration_id: 'iteration-2',
        proposal: { terminal: 'synthesis', tasks: [{ task_id: 'plan-2', executor: 'other_answer', intent: 'answer', instructions: 'Сформировать ответ' }] },
      }),
    ]);

    const [first, second] = projectTraceStages(state);
    const stageTarget = resolveTraceInspectionTarget(state, 'planner_iteration:iteration-1');
    const plannerTarget = resolveTraceInspectionTarget(state, first.executorRuns[0].inspectorKey);
    expect(first.kind).toBe('iteration');
    expect(first.steps[0].kind).toBe('planner_decision');
    expect(stageTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'План', 'Результат', 'RAW']);
    expect(plannerTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'План', 'RAW']);
    expect(first.plan?.tasks.map((task) => task.taskId)).toEqual(['plan-1']);
    expect(second.plan?.tasks.map((task) => task.taskId)).toEqual(['plan-2']);
    expect(first.executorRuns[0].calls).toHaveLength(1);
    expect(first.executorRuns[0].taskPresentation).toMatchObject({ executor: 'planner', title: 'Принятие решения по плану' });
  });

  it('shows planner RBAC from the canonical event and older orchestrator snapshot', () => {
    const audit = { allowed: ['viewer'], denied_by_rbac: ['hidden'] };
    const base = [
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'planner-1', role: 'planner', context_snapshot: { rbac: audit } }),
      event(2, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1' }),
      event(3, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(4, 'access_snapshot', { entity_type: 'planner', entity_id: 'iteration-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', items: [{ kind: 'agent', key: 'viewer', label: 'Просмотрщик', status: 'available' }] }),
    ];
    for (const events of [base, [...base, event(5, 'rbac_snapshot', {
      entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', rbac: audit,
    })]]) {
      const state = replayRuntimeJournal(events);
      const planner = projectTraceStages(state)[0].executorRuns[0];
      const target = resolveTraceInspectionTarget(state, planner.inspectorKey);
      expect(target?.tabs.map((item) => item.label)).toContain('Доступ');
      expect(planner.access?.rows).toContainEqual({ kind: 'Агент', name: 'viewer', allowed: true, reason: 'Разрешён эффективной политикой' });
      expect(planner.access?.rows).toContainEqual({ kind: 'Агент', name: 'hidden', allowed: false, reason: 'Запрещён RBAC' });
      expect(planner.accessSnapshot?.items).toContainEqual(expect.objectContaining({ key: 'viewer', label: 'Просмотрщик', status: 'available' }));
    }
  });

  it('shows planned tasks and a checkpoint before task execution starts', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', iteration_number: 1 }),
      event(2, 'llm_request', { entity_type: 'llm_call', entity_id: 'planner-call', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', purpose: 'planning_decision' }),
      event(3, 'llm_response', { entity_type: 'llm_call', entity_id: 'planner-call', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', purpose: 'planning_decision', status: 'completed' }),
      event(4, 'plan_iteration_applied', {
        entity_type: 'plan', entity_id: 'plan-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', iteration_id: 'iteration-1',
        proposal: { terminal: 'synthesis', tasks: [{ task_id: 'network', executor: 'net.engineer', intent: 'fill_template', instructions: 'Заполнить заявку' }] },
      }),
      event(5, 'task_planned', {
        entity_type: 'task', entity_id: 'task-entity-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1',
        task_id: 'network', executor: 'net.engineer', intent: 'fill_template', instructions: 'Заполнить заявку', status: 'waiting',
      }),
      event(6, 'checkpoint_planned', {
        entity_type: 'checkpoint', entity_id: 'checkpoint-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1',
        declared_next: 'synthesis', status: 'waiting',
      }),
    ]);

    const stage = projectTraceStages(state)[0];
    expect(stage.entity.status).toBe('running');
    expect(stage.steps.map((step) => [step.title, step.executorRuns[0]?.entity.status])).toEqual([
      ['Принятие решения по плану', 'completed'],
      ['fill_template', 'waiting'],
      ['Контрольная точка', 'waiting'],
    ]);
    expect(stage.steps[1].executorRuns[0].executorName).toBe('net.engineer');
    expect(stage.steps[2].executorRuns[0].executorType).toBe('CHECKPOINT');
  });

  it('keeps the planner delta separate from the accumulated plan and shows both checkpoints', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'planner-1', role: 'planner' }),
      event(2, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', iteration: 1 }),
      event(3, 'plan_iteration_applied', { entity_type: 'plan', entity_id: 'plan-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', iteration_id: 'iteration-1', proposal: { terminal: 'planner', tasks: [{ task_id: 'netbox_1', executor: 'inventory.netbox', intent: 'Инвентарь', instructions: 'Собрать' }] } }),
      event(4, 'task_planned', { entity_type: 'task', entity_id: 'task-entity-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', plan_id: 'plan-1', iteration_id: 'iteration-1', task_id: 'netbox_1', executor: 'inventory.netbox', intent: 'Инвентарь' }),
      event(5, 'checkpoint_planned', { entity_type: 'checkpoint', entity_id: 'cp-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', plan_id: 'plan-1', iteration_id: 'iteration-1', declared_next: 'planner' }),
      event(6, 'task_completed', { entity_type: 'task', entity_id: 'task-entity-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', plan_id: 'plan-1', task_id: 'netbox_1' }),
      event(7, 'checkpoint_decided', { entity_type: 'checkpoint', entity_id: 'cp-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', plan_id: 'plan-1', iteration_id: 'iteration-1', declared_next: 'planner', effective_next: 'planner' }),
      event(8, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-2', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', iteration: 2 }),
      event(9, 'llm_request', { entity_type: 'llm_call', entity_id: 'planner-call-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', purpose: 'planning_decision' }),
      event(10, 'plan_iteration_applied', { entity_type: 'plan', entity_id: 'plan-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', iteration_id: 'iteration-2', proposal: { terminal: 'synthesis', tasks: [] } }),
      event(11, 'checkpoint_planned', { entity_type: 'checkpoint', entity_id: 'cp-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', plan_id: 'plan-1', iteration_id: 'iteration-2', declared_next: 'synthesis' }),
    ]);
    const stage = projectTraceStages(state).find(item => item.entity.id === 'iteration-2');
    expect(stage?.plan?.tasks).toHaveLength(0);
    expect(stage?.fullPlan?.tasks).toMatchObject([{ taskId: 'netbox_1', status: 'Готово' }]);
    expect(stage?.fullPlan?.entries?.filter(item => item.kind === 'checkpoint')).toHaveLength(2);
    const plannerStep = stage?.steps.find(step => step.kind === 'planner_decision');
    expect(plannerStep).toBeDefined();
    expect(resolveTraceInspectionTarget(state, plannerStep!.key)?.tabs.map(tab => tab.id)).toContain('plan');
  });

  it('explains the declared and effective checkpoint transition', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'planner-1', role: 'planner' }),
      event(2, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', iteration: 1 }),
      event(3, 'llm_request', { entity_type: 'llm_call', entity_id: 'call-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(4, 'llm_response', { entity_type: 'llm_call', entity_id: 'call-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', status: 'completed', terminal: true }),
      event(5, 'checkpoint_planned', { entity_type: 'checkpoint', entity_id: 'checkpoint-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', declared_next: 'planner', status: 'waiting', iteration_id: 'iteration-1' }),
      event(6, 'checkpoint_decided', { entity_type: 'checkpoint', entity_id: 'checkpoint-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', declared_next: 'planner', effective_next: 'planner', reason: 'task_failure', status: 'completed', iteration_id: 'iteration-1' }),
    ]);

    const checkpoint = projectTraceStages(state)[0].steps.find((step) => step.entity.type === 'checkpoint')?.executorRuns[0];
    expect(checkpoint?.checkpoint).toEqual({
      declaredNext: 'planner', effectiveNext: 'planner', reason: 'task_failure', iterationId: 'iteration-1', decided: true,
    });
    expect(resolveTraceInspectionTarget(state, checkpoint!.inspectorKey)?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Решение', 'RAW']);
  });

  it('shows the plan failure code on the failed replan iteration', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'planner-1', role: 'planner' }),
      event(2, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', iteration: 1 }),
      event(3, 'llm_request', { entity_type: 'llm_call', entity_id: 'call-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(4, 'llm_response', { entity_type: 'llm_call', entity_id: 'call-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', status: 'completed', terminal: true }),
      event(5, 'plan_iteration_applied', { entity_type: 'plan', entity_id: 'plan-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', iteration_id: 'iteration-1', plan_id: 'plan-1' }),
      event(6, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-2', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', iteration: 2 }),
      event(7, 'llm_request', { entity_type: 'llm_call', entity_id: 'call-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2' }),
      event(8, 'llm_response', { entity_type: 'llm_call', entity_id: 'call-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', status: 'completed', terminal: true }),
      event(9, 'planner_iteration_end', { entity_type: 'planner_iteration', entity_id: 'iteration-2', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', status: 'failed' }),
      event(10, 'plan_failed', { entity_type: 'plan', entity_id: 'plan-1', plan_id: 'plan-1', status: 'failed', error_code: 'planner_checkpoint_failed' }),
    ]);

    const stage = projectTraceStages(state).find((item) => item.entity.id === 'iteration-2');
    expect(stage?.failure).toEqual({ label: 'Не удалось завершить перепланирование', code: 'planner_checkpoint_failed', message: undefined });
    expect(resolveTraceInspectionTarget(state, stage!.entity.key)?.tabs.map((item) => item.label)).toContain('Ошибка');
  });

  it('replaces a planned-task placeholder with its execution by task entity id', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', iteration_number: 1 }),
      event(2, 'task_planned', {
        entity_type: 'task', entity_id: 'task-entity-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1',
        task_id: 'network', executor: 'net.engineer', intent: 'fill_template', status: 'waiting',
      }),
      event(3, 'step_start', {
        entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1',
        task_id: 'network', task_entity_id: 'task-entity-1', title: 'Заполнить заявку',
      }),
      event(4, 'agent_start', {
        entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1',
        task_id: 'network', task_entity_id: 'task-entity-1', agent_slug: 'net.engineer', task_title: 'Заполнить заявку',
      }),
    ]);

    const stage = projectTraceStages(state)[0];
    expect(stage.steps).toHaveLength(1);
    expect(stage.steps[0]).toMatchObject({ key: 'task:task-entity-1', title: 'Заполнить заявку' });
    expect(stage.steps[0].executorRuns[0].entity.key).toBe('agent_execution:agent-1');
  });

  it('groups a logical task by explicit attempt and step identifiers', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'task_planned', { entity_type: 'task', entity_id: 'task-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', task_id: 'lookup', title: 'Найти данные' }),
      event(3, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', task_id: 'lookup', task_entity_id: 'task-1', attempt_id: 'attempt-1', step_id: 'step-1', title: 'Первая попытка' }),
      event(4, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker', task_entity_id: 'task-1', attempt_id: 'attempt-1' }),
      event(5, 'step_start', { entity_type: 'step', entity_id: 'step-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', task_id: 'lookup', task_entity_id: 'task-1', attempt_id: 'attempt-2', step_id: 'step-2', title: 'Повторная попытка' }),
      event(6, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-2', parent_entity_type: 'step', parent_entity_id: 'step-2', agent_slug: 'worker', task_entity_id: 'task-1', attempt_id: 'attempt-2' }),
    ]);
    const taskSteps = projectTraceStages(state)[0].steps.filter((step) => step.taskId === 'lookup');
    expect(taskSteps).toHaveLength(1);
    expect(taskSteps[0].attempts?.map((attempt) => attempt.id)).toEqual(['attempt-1', 'attempt-2']);
    expect(taskSteps[0].attempts?.map((attempt) => attempt.steps.length)).toEqual([1, 1]);
    expect(taskSteps[0].executorRuns.map((executor) => executor.entity.id)).toEqual(['agent-1', 'agent-2']);
  });

  it('projects memory context and keeps a minimal task presentation when no plan exists', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'memory-preparation', role: 'memory_preparation' }),
      event(2, 'agent_start', { entity_type: 'agent_execution', entity_id: 'selector-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-preparation', agent_slug: 'memory_preparation', task_title: 'Отбор контекста' }),
      event(3, 'status', {
        entity_type: 'agent_execution', entity_id: 'selector-1', parent_entity_type: 'orchestrator', parent_entity_id: 'memory-preparation',
        stage: 'memory_context_prepared', fallback: true, selected_facts: 2, selected_projects: 1,
        memory_context: [{ type: 'fact', subject: 'role', value: 'engineer' }], ambiguities: ['СРК может означать несколько терминов'],
      }),
    ]);

    const stage = projectTraceStages(state)[0];
    const target = resolveTraceInspectionTarget(state, stage.executorRuns[0].inspectorKey);
    expect(stage.kind).toBe('memory_preparation');
    expect(stage.steps[0].kind).toBe('memory_selection');
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Задача', 'Память', 'RAW']);
    expect(stage.steps[0].taskPresentation).toMatchObject({ title: 'Отбор контекста', executor: 'memory_preparation' });
    expect(stage.executorRuns[0].memoryContext).toEqual({
      fallback: true,
      selectedFacts: 2,
      selectedProjects: 1,
      selectedGlossary: 0,
      selectedMemoryItems: 0,
      context: [{ type: 'fact', scope: 'unknown', subject: 'role', value: 'engineer' }],
      ambiguities: ['СРК может означать несколько терминов'],
      sourceCheckReasons: [],
    });
  });

  it('projects the production memory-recall selector contract', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'recall-1', role: 'memory_recall' }),
      event(2, 'agent_start', { entity_type: 'agent_execution', entity_id: 'selector-1', parent_entity_type: 'orchestrator', parent_entity_id: 'recall-1', agent_slug: 'memory_selector' }),
      event(3, 'status', {
        entity_type: 'agent_execution', entity_id: 'selector-1', parent_entity_type: 'orchestrator', parent_entity_id: 'recall-1',
        stage: 'memory_context_prepared', selected_facts: 1, selected_projects: 1, selected_glossary: 1, selected_memory_items: 1,
        search_scope: { direction: 'policy' }, memory_context: {
          durable_facts: [{ scope: 'user', subject: 'language', value: 'ru' }],
          relevant_projects: [{ key: 'CORE', name: 'Core' }],
          resolved_terms: [{ term: 'SLO', description: 'Целевой уровень', aliases: ['sla'] }],
          applicable_rules: [{ scope: 'project', kind: 'rule', subject: 'deploy', content: { value: 'approval' }, confidence: 0.9, source_references: [{ id: 'doc-1' }] }],
          rag_reasons: ['uncertain_memory:1'],
        },
      }),
      event(4, 'agent_end', { entity_type: 'agent_execution', entity_id: 'selector-1', parent_entity_type: 'orchestrator', parent_entity_id: 'recall-1', status: 'completed' }),
    ]);
    const selector = projectTraceStages(state)[0].executorRuns[0];
    expect(projectTraceStages(state)[0].kind).toBe('memory_preparation');
    expect(selector.kind).toBe('memory_selector');
    expect(selector.memoryContext).toMatchObject({ selectedGlossary: 1, selectedMemoryItems: 1, sourceCheckReasons: ['uncertain_memory:1'] });
    expect(selector.memoryContext?.context).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: 'fact', subject: 'language' }),
      expect.objectContaining({ type: 'knowledge', subject: 'deploy' }),
    ]));
  });

  it('uses synthesis presentation kinds and the shared executor tab policy', () => {
    const state = replayRuntimeJournal([
      event(1, 'synthesis_start', { entity_type: 'synthesis_run', entity_id: 'synthesis-1' }),
      event(2, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1', purpose: 'final_answer' }),
      event(3, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1', result_kind: 'answer', content: 'Готово', terminal: true }),
    ]);

    const stage = projectTraceStages(state)[0];
    const target = resolveTraceInspectionTarget(state, 'synthesis_run:synthesis-1');
    const executorTarget = resolveTraceInspectionTarget(state, 'executor:synthesis_run:synthesis-1');
    const callTarget = resolveTraceInspectionTarget(state, 'llm_call:llm-1');
    expect(stage.kind).toBe('synthesis');
    expect(stepFor(stage).kind).toBe('synthesis');
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'RAW']);
    expect(executorTarget?.kind).toBe('executor');
    expect(executorTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'RAW']);
    expect(callTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Запрос', 'Ответ', 'RAW']);
    if (callTarget?.kind === 'call') {
      expect(callTarget.call.requestView).toMatchObject({ purpose: 'Финальный ответ', messages: [] });
      expect(callTarget.call.responseView).toMatchObject({ resultKind: 'answer', terminal: true, content: { kind: 'text', text: 'Готово' } });
    }
  });

  it('keeps synthesizer sources and attachments on its result entity', () => {
    const state = replayRuntimeJournal([
      event(1, 'synthesis_start', { entity_type: 'synthesis_run', entity_id: 'synthesis-1' }),
      event(2, 'status', { entity_type: 'synthesis_run', entity_id: 'synthesis-1', stage: 'final_answer_marker', content: 'Готово', sources: [{ id: 'doc-1' }], attachments: [{ artifact_id: 'a-1' }] }),
    ]);
    const synthesizer = projectTraceStages(state)[0].executorRuns[0];
    expect(synthesizer.result).toMatchObject({ output: 'Готово', sources: [{ id: 'doc-1' }], artifacts: [{ artifact_id: 'a-1' }] });
  });

  it('builds one labelled LLM transcript and a safe expandable tool result projection', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'llm_request', {
        entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1',
        messages: [
          { role: 'system', content: 'Следуй правилам' },
          { role: 'user', content: 'Найди документ' },
          { role: 'tool', content: '{"total":2}' },
        ],
      }),
      event(5, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', content: 'Готово', status: 'completed' }),
      event(6, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'collection.document.search', arguments: { query: 'СРК' } }),
      event(7, 'tool_result', {
        entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', success: true,
        result: { success: true, data: { total: 2, artifact_id: 'private', rows: [{ title: 'Регламент' }] } },
      }),
    ]);

    const llmTarget = resolveTraceInspectionTarget(state, 'llm_call:llm-1');
    const toolTarget = resolveTraceInspectionTarget(state, 'tool_call:tool-1');
    if (llmTarget?.kind === 'call') {
      expect(llmTarget.call.requestView.messageTranscript).toContain('Системные инструкции');
      expect(llmTarget.call.requestView.messageTranscript).toContain('Запрос пользователя');
      expect(llmTarget.call.requestView.messageTranscript).toContain('Контекст инструмента');
    } else {
      throw new Error('LLM call projection is missing');
    }
    if (toolTarget?.kind === 'call') {
      expect(toolTarget.call.responseView?.toolResult).toMatchObject({
        success: true,
        summary: 'Всего в источнике: 2',
        data: { total: 2, rows: [{ title: 'Регламент' }] },
      });
    } else {
      throw new Error('Tool call projection is missing');
    }
  });

  it('projects a terminal executor result without making the viewer read journal events', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker', executor_name: 'Worker' }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'collection.document.search' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', success: true, result: { success: true, data: [] } }),
      event(6, 'agent_end', {
        entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1',
        status: 'completed', summary: 'Готовый результат', completion_kind: 'answer', sufficient_for_phase: true,
        needs: [{ key: 'follow_up' }], artifacts: [{ file_name: 'answer.txt' }],
      }),
    ]);

    const result = projectTraceStages(state)[0].steps[0].executorRuns[0].result;
    expect(result).toEqual(expect.objectContaining({
      name: 'Worker', status: 'completed', statusLabel: 'Готово', output: 'Готовый результат',
      completionKind: 'answer', sufficientForPhase: true, needs: [{ key: 'follow_up' }], artifacts: [{ file_name: 'answer.txt' }],
      operations: { total: 1, succeeded: 1, failed: 0 },
    }));
  });

  it('projects TaskResult text and arbitrary structured data without exposing the result envelope', () => {
    const executor = projectAgentExecutor({ result: {
      protocol_version: 2,
      outcome: 'completed',
      completion: 'fulfilled',
      description: 'Ответ агента',
      answer: 'Краткий текст',
      structured_response: { enabled: false, retries: 0, note: null },
      outputs: { enabled: false, retries: 0, note: null },
      needs: [], attachments: [], sources: [], diagnostics: [],
      verified: { receipts: [{ success: true, operation: 'collection.document.search', retrieval: true, result_fingerprint: 'secret-fingerprint', result_id: 'secret-result' }] },
    } });

    expect(executor.result.agentResponse).toMatchObject({
      answer: 'Краткий текст',
      hasStructuredData: true,
      structuredData: { enabled: false, retries: 0, note: null },
      completion: 'fulfilled',
      outcome: 'completed',
      actions: [{ label: 'collection · document · search', retrieval: true }],
    });
    expect(executor.result.output).toEqual({ enabled: false, retries: 0, note: null });
    expect(JSON.stringify(executor.result.agentResponse)).not.toContain('secret-fingerprint');
    expect(JSON.stringify(executor.result.agentResponse)).not.toContain('secret-result');
    expect(JSON.stringify(executor.result.agentResponse)).not.toContain('protocol_version');
  });

  it('distinguishes omitted structured response from explicit null and preserves false, zero, objects and arrays', () => {
    const omitted = projectAgentExecutor({ result: { outcome: 'completed', completion: 'fulfilled', structured_response: null, outputs: {} } });
    const explicitNull = projectAgentExecutor({ result: { outcome: 'completed', completion: 'fulfilled', structured_response: null, outputs: { structured_response: null } } });
    expect(omitted.result.agentResponse).toMatchObject({ hasStructuredData: false });
    expect(explicitNull.result.agentResponse).toMatchObject({ hasStructuredData: true, structuredData: null });

    for (const value of [false, 0, {}, []]) {
      const executor = projectAgentExecutor({ result: { outcome: 'completed', completion: 'fulfilled', structured_response: value, outputs: {} } });
      expect(executor.result.agentResponse).toMatchObject({ hasStructuredData: true, structuredData: value });
    }
  });

  it('projects every recorded interaction choice as passive response details', () => {
    const executor = projectAgentExecutor({ result: {
      outcome: 'needs_dependency', completion: 'needs',
      interaction: { question: 'Какой филиал?', response_type: 'boolean', options: ['Да', 'Нет', 3, '', ...Array.from({ length: 15 }, (_, index) => `Вариант ${index}`)] },
    } });

    expect(executor.result.agentResponse?.interaction).toMatchObject({
      kind: 'confirmation', question: 'Какой филиал?', responseTypeLabel: 'Ответ «да» или «нет»',
      options: ['Да', 'Нет', ...Array.from({ length: 15 }, (_, index) => `Вариант ${index}`)],
    });
  });

  it('preserves all recorded sources and successful receipts in the typed result', () => {
    const sources = Array.from({ length: 24 }, (_, index) => ({ title: `Источник ${index}` }));
    const receipts = Array.from({ length: 15 }, (_, index) => ({
      success: true, operation: `collection.document.search_${index}`, retrieval: true,
    }));
    const executor = projectAgentExecutor({ result: {
      outcome: 'completed', completion: 'fulfilled', sources,
      verified: { receipts },
    } });

    expect(executor.result.agentResponse?.sources).toHaveLength(24);
    expect(executor.result.agentResponse?.actions).toHaveLength(15);
  });

  it('localizes known agent receipt operations and keeps unknown names readable', () => {
    const executor = projectAgentExecutor({ result: {
      outcome: 'completed', completion: 'fulfilled',
      verified: { receipts: ['netbox_get_objects', 'result.sql', 'result.analyze', 'custom.lookup'].map(operation => ({
        success: true, operation, retrieval: true,
      })) },
    } });

    expect(executor.result.agentResponse?.actions.map(action => action.label)).toEqual([
      'Получение объектов NetBox',
      'Анализ сохранённых данных',
      'Анализ сохранённых данных',
      'custom · lookup',
    ]);
  });

  it('groups only declared diagnostics and keeps result notes in structured data', () => {
    const executor = projectAgentExecutor({ result: {
      outcome: 'completed', completion: 'fulfilled',
      structured_response: { notes: 'The source returned a partial inventory.' },
      outputs: {},
      diagnostics: [
        { code: 'schema_deviation' },
        { code: 'schema_deviation' },
        { code: 'advisory_schema_invalid' },
      ],
    } });

    expect(executor.result.agentResponse?.diagnostics).toMatchObject([
      { label: 'Данные отличаются от рекомендованного формата', count: 2, details: ['Некоторые поля не совпали с рекомендуемым описанием. Полученные значения сохранены в результате.'] },
      { label: 'Не удалось проверить рекомендованный формат', count: 1, details: ['Рекомендуемую схему не удалось проверить. Просмотрите сохранённый результат ниже.'] },
    ]);
    expect(executor.result.agentResponse?.structuredData).toEqual({ notes: 'The source returned a partial inventory.' });
  });

  it('localizes known missing required artifact limitations over technical messages', () => {
    const executor = projectAgentExecutor({ result: {
      outcome: 'unfulfillable', completion: 'unfulfillable', reason_code: 'required_artifact_missing',
      limitation: { code: 'required_artifact_missing', message: 'required_artifact_missing: artifact registry returned null' },
    } });

    expect(executor.result.agentResponse?.limitation?.message).toBe('Не создан обязательный файл');
  });

  it('adapts legacy output slots without displaying evidence references as answer data', () => {
    const valueSlot = projectAgentExecutor({ result: {
      outcome: 'completed', completion: 'fulfilled',
      outputs: { enabled: { kind: 'value', value: false }, evidence: { kind: 'evidence', ref: 'private-ref' } },
    } });
    const evidenceOnly = projectAgentExecutor({ result: {
      outcome: 'completed', completion: 'fulfilled',
      outputs: { evidence: { kind: 'evidence', ref: 'private-ref' } },
    } });

    expect(valueSlot.result.agentResponse).toMatchObject({ hasStructuredData: true, structuredData: { enabled: false } });
    expect(evidenceOnly.result.agentResponse).toMatchObject({ hasStructuredData: false });
    expect(JSON.stringify(evidenceOnly.result.agentResponse)).not.toContain('private-ref');
  });

  it('uses only a final explicitly owned by the selected agent and parses JSON data as structured', () => {
    const owned = event(4, 'final', {
      entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1',
      content: '{"items":[{"name":"device-a"}]}',
    });
    const neighbor = event(4, 'final', {
      entity_type: 'agent_execution', entity_id: 'agent-2', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-2',
      content: 'Не относится к выбранному агенту',
    });
    const withOwned = projectAgentExecutor({}, [owned]);
    const withNeighborOnly = projectAgentExecutor({}, [neighbor]);

    expect(withOwned.result.agentResponse).toMatchObject({ hasStructuredData: true, structuredData: { items: [{ name: 'device-a' }] } });
    expect(withNeighborOnly.result.agentResponse?.answer).toBeUndefined();
    expect(withNeighborOnly.result.agentResponse?.hasStructuredData).toBe(false);
  });

  it('keeps JSON objects with legacy-looking keys as domain data unless they match the completion contract', () => {
    const domainValues = [
      { answer: 42, device_id: 'router-1' },
      { report: { rows: [1, 2] }, device_id: 'router-2' },
      { outputs: { count: 3 }, device_id: 'router-3' },
      { completion: 'fulfilled', device_id: 'router-4' },
    ];
    for (const value of domainValues) {
      const owned = event(4, 'final', {
        entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1',
        content: JSON.stringify(value),
      });
      const executor = projectAgentExecutor({}, [owned]);
      expect(executor.result.agentResponse).toMatchObject({ hasStructuredData: true, structuredData: value });
    }
  });

  it('projects safe sources from the selected agent final sidecar', () => {
    const owned = event(4, 'final', {
      entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1',
      content: 'Найдена запись.',
      sources: [{ title: 'Каталог устройств', url: 'https://inventory.example/devices' }],
    });
    const executor = projectAgentExecutor({}, [owned]);

    expect(executor.result.agentResponse?.answer).toBe('Найдена запись.');
    expect(executor.result.agentResponse?.sources).toEqual([{ label: 'Каталог устройств', href: 'https://inventory.example/devices' }]);
  });

  it('maps standalone agent completion claims to consistent result, info, and timeline statuses', () => {
    for (const [claim, expected] of [['fulfilled', 'completed'], ['needs', 'waiting']] as const) {
      const executor = projectAgentExecutor({ outcome: claim });
      expect(executor.result.status).toBe(expected);
      expect(executor.info.status).toBe(expected);
      expect(executor.entity.status).toBe(expected);
    }

    const paused = projectAgentExecutor({ status: 'paused', outcome: 'fulfilled' });
    expect(paused.result.status).toBe('paused');
    expect(paused.entity.status).toBe('paused');
  });

  it('uses the final answer marker as the synthesizer result', () => {
    const state = replayRuntimeJournal([
      event(1, 'synthesis_start', { entity_type: 'synthesis_run', entity_id: 'synthesis-1' }),
      event(2, 'final_answer_marker', { entity_type: 'run', entity_id: 'run-1', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1', content: 'Готовый ответ' }),
      event(3, 'synthesis_end', { entity_type: 'synthesis_run', entity_id: 'synthesis-1', status: 'completed' }),
    ]);

    expect(projectTraceStages(state)[0].executorRuns[0].result).toMatchObject({
      status: 'completed', output: 'Готовый ответ',
    });
  });

  it('projects an executor failure with its safe error message', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'error', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', agent_execution_id: 'agent-1', safe_message: 'Доступ к источнику отсутствует' }),
    ]);

    expect(projectTraceStages(state)[0].steps[0].executorRuns[0].result).toMatchObject({
      status: 'failed', statusLabel: 'Ошибка', message: 'Доступ к источнику отсутствует',
    });
  });

  it('does not show an unfulfillable task as a successful executor', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'viewer' }),
      event(4, 'agent_end', {
        entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1',
        status: 'completed', outcome: 'unfulfillable', summary: 'Недостаточно данных',
      }),
    ]);

    const executor = projectTraceStages(state)[0].steps[0].executorRuns[0];
    expect(executor.entity.status).toBe('unfulfillable');
    expect(executor.result.status).toBe('unfulfillable');
  });

  it('shows snapshot tabs only when the corresponding projection exists', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker', task_title: 'Выполнение' }),
      event(4, 'rbac_snapshot', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', rbac: { agent_access: { slug: 'worker', allowed: true, reason: 'RBAC passed' }, collection_filter: { allowed: ['docs'] } } }),
      event(5, 'access_snapshot', { entity_type: 'agent', entity_id: 'agent-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', agent_description: 'Агент для работы с документами', items: [{ kind: 'source', key: 'docs', label: 'Документы', description: 'Корпоративная база документов', status: 'unavailable', reason_code: 'blocked_by_rbac', reason: 'Нет доступа к источнику', children: [{ kind: 'tool', key: 'search', label: 'Поиск', description: 'Ищет документы по запросу', source_label: 'Confluence', status: 'unavailable', reason: 'Источник недоступен', risk_level: 'low' }] }] }),
      event(6, 'budget_snapshot', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', own: { llm_calls: 1 }, limits: { llm_calls: 2 } }),
      event(7, 'preflight_started', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1' }),
      event(8, 'preflight_completed', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', status: 'ok', missing: { tools: [], collections: [], credentials: [] } }),
      event(9, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', messages: [{ role: 'system', content: 'prompt' }] }),
      event(10, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', content: 'ok', status: 'completed' }),
      event(11, 'agent_end', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', status: 'completed', summary: 'Готово' }),
      event(12, 'access_snapshot', { entity_type: 'agent', entity_id: 'agent-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-2', items: [{ kind: 'source', key: 'wrong', label: 'Чужой источник', status: 'available' }] }),
    ]);
    const stages = projectTraceStages(state);
    const executorTarget = resolveTraceInspectionTarget(state, 'agent_execution:agent-1');
    const callTarget = resolveTraceInspectionTarget(state, 'llm_call:llm-1');
    expect(executorTarget?.tabs.map((item) => item.label)).toEqual(['Задача', 'Результат', 'Промпт', 'Доступ', 'Лимиты и расход', 'RAW']);
    if (executorTarget?.kind === 'executor') {
      expect(executorTarget.executor.access?.rows).toContainEqual({ kind: 'Агент', name: 'worker', allowed: true, reason: 'RBAC passed' });
      expect(executorTarget.executor.access?.rows).toContainEqual({ kind: 'Коллекция', name: 'docs', allowed: true, reason: 'Доступна выбранному агенту' });
      expect(executorTarget.executor.accessSnapshot).toMatchObject({
        entityType: 'agent',
        agentDescription: 'Агент для работы с документами',
        items: [{ kind: 'source', key: 'docs', description: 'Корпоративная база документов', status: 'unavailable', children: [{ kind: 'tool', key: 'search', description: 'Ищет документы по запросу', sourceLabel: 'Confluence', riskLevel: 'low' }] }],
      });
    }
    expect(callTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Запрос', 'Ответ', 'RAW']);
    expect(stages[0].executorRuns[0].prompt?.text).toBe('prompt');
  });

  it('shows the RBAC tab only after an access decision is logged', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'agent_execution:agent-1');
    expect(target?.tabs.map((item) => item.label)).toEqual(['Задача', 'RAW']);
    expect(target?.tabs.map((item) => item.label)).not.toContain('Доступ');
    expect(target?.tabs.map((item) => item.label)).not.toContain('Готовность');
    expect(target?.kind).toBe('executor');
    if (target?.kind === 'executor') expect(target.executor.access).toBeUndefined();
  });

  it('separates configured tool overrides, effective operations, and suppressed publication', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', title: 'Выполнить задачу' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'sandbox_override_snapshot', {
        entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'task', parent_entity_id: 'task-1',
        configured: { publication: { 'tool-disabled': false }, semantics: { 'tool-effective': { description: 'Configured' } } },
        effective_operations: [{ discovered_tool_id: 'tool-effective', publication_configured: true, published_effective: true, configured: { description: 'Configured' }, effective: { description: 'Effective' } }],
        suppressed_publication: { 'tool-disabled': 'disabled_by_sandbox_override' },
      }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'agent_execution:agent-1');
    expect(target?.tabs.map((item) => item.label)).toContain('Операции');
    if (target?.kind === 'executor') {
      expect(target.executor.toolOverrides).toMatchObject({
        configuredPublication: { 'tool-disabled': false },
        effectiveOperations: [{ toolId: 'tool-effective', publishedEffective: true }],
        suppressedPublication: [{ toolId: 'tool-disabled', reason: 'disabled_by_sandbox_override' }],
      });
    }
  });

  it('shows a denied agent decision even when preflight fails', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'rbac_snapshot', { entity_type: 'agent_execution', entity_id: 'agent-1', rbac: { agent_access: { slug: 'worker', allowed: false, reason: 'Запрещён runtime RBAC' } } }),
      event(5, 'preflight_failed', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', reason: 'unavailable' }),
    ]);
    const target = resolveTraceInspectionTarget(state, 'agent_execution:agent-1');
    expect(target?.tabs.map((item) => item.label)).toContain('Доступ');
    if (target?.kind === 'executor') expect(target.executor.access?.rows).toContainEqual({
      kind: 'Агент', name: 'worker', allowed: false, reason: 'Запрещён runtime RBAC',
    });
  });

  it('projects agent work statistics and only its configured limits', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'worker' }),
      event(4, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1' }),
      event(5, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', status: 'completed', tokens_in: 100, tokens_out: 50, tokens_total: 150 }),
      event(6, 'protocol_retry', { entity_type: 'run', entity_id: 'run-1', llm_call_id: 'llm-1' }),
      event(7, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'first' }),
      event(8, 'tool_result', { entity_type: 'tool_call', entity_id: 'tool-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', success: false }),
      event(9, 'tool_call', { entity_type: 'tool_call', entity_id: 'tool-2', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', tool: 'second' }),
      event(10, 'tool_result', { entity_type: 'tool_call', entity_id: 'tool-2', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', success: true }),
      event(11, 'budget_snapshot', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', snapshot: { llm_calls: { used: 1, limit: 2, remaining: 1 }, tool_calls: { used: 2 }, tokens_total: { used: 150, limit: 200, remaining: 50 }, tokens_in: { used: 100 }, tokens_out: { used: 50 } } }),
      event(12, 'agent_end', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', status: 'completed', summary: 'Готово' }),
    ]);

    const executor = projectTraceStages(state)[0].executorRuns[0];
    expect(executor.info.statistics).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'llm_calls', value: 1, limit: expect.objectContaining({ limit: 2 }) }),
      expect.objectContaining({ key: 'tool_calls', value: 2 }),
      expect.objectContaining({ key: 'tokens_in', label: 'Входные токены', value: 100 }),
      expect.objectContaining({ key: 'tokens_out', label: 'Выходные токены', value: 50 }),
      expect.objectContaining({ key: 'tokens_total', label: 'Всего токенов', value: 150, limit: expect.objectContaining({ limit: 200 }) }),
      expect.objectContaining({ key: 'llm_retries', value: 1 }),
      expect.objectContaining({ key: 'tool_errors', value: 1 }),
    ]));
    expect(executor.limits?.rows.map((row) => row.key)).toEqual(['llm_calls', 'tokens_total']);
  });

  it('separates input, output and total token usage for planner and synthesizer', () => {
    const state = replayRuntimeJournal([
      event(1, 'run_start', { entity_type: 'run', entity_id: 'run-1' }),
      event(2, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'planner-1', parent_entity_type: 'run', parent_entity_id: 'run-1', role: 'planner' }),
      event(3, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', iteration: 1 }),
      event(4, 'llm_request', { entity_type: 'llm_call', entity_id: 'planner-call', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', purpose: 'planning_decision' }),
      event(5, 'llm_response', { entity_type: 'llm_call', entity_id: 'planner-call', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', status: 'completed', terminal: true, tokens_in: 110, tokens_out: 11, tokens_total: 121 }),
      event(6, 'synthesis_start', { entity_type: 'synthesis_run', entity_id: 'synthesis-1', parent_entity_type: 'run', parent_entity_id: 'run-1' }),
      event(7, 'llm_request', { entity_type: 'llm_call', entity_id: 'synthesis-call', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1', purpose: 'final_answer' }),
      event(8, 'llm_response', { entity_type: 'llm_call', entity_id: 'synthesis-call', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1', status: 'completed', terminal: true, tokens_in: 220, tokens_out: 22, tokens_total: 242 }),
    ]);

    const stages = projectTraceStages(state);
    const usage = (kind: string) => stages.find((stage) => stage.kind === kind)?.executorRuns[0]?.info.statistics
      .filter((item) => item.key.startsWith('tokens_'))
      .map(({ key, value }) => [key, value]);
    expect(usage('iteration')).toEqual([['tokens_in', 110], ['tokens_out', 11], ['tokens_total', 121]]);
    expect(usage('synthesis')).toEqual([['tokens_in', 220], ['tokens_out', 22], ['tokens_total', 242]]);
  });
});

describe('projectTraceRun', () => {
  it('uses only the canonical final answer marker and normalizes attachments', () => {
    const state = replayRuntimeJournal([
      event(1, 'delta', { entity_type: 'run', entity_id: 'run-1', content: 'partial ' }),
      event(2, 'final', {
        entity_type: 'run', entity_id: 'run-1', content: 'Готово',
        attachments: [
          { artifact_id: 'a-1', file_name: 'answer.txt' },
          { artifact_id: 'a-1', file_name: 'duplicate.txt' },
          { artifact_id: '', file_name: 'invalid.txt' },
        ],
      }),
      event(3, 'run_end', { entity_type: 'run', entity_id: 'run-1', status: 'completed' }),
      event(4, 'final_answer_marker', {
        entity_type: 'run', entity_id: 'run-1', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1',
        status: 'completed', content: 'Канонический ответ', sources: [{ id: 'source-1' }],
        attachments: [{ artifact_id: 'a-1', file_name: 'answer.txt' }, { artifact_id: 'a-1', file_name: 'duplicate.txt' }],
      }),
    ]);
    expect(projectTraceRun(state)).toMatchObject({
      runId: 'run-1', status: 'completed', finalContent: 'Канонический ответ', sources: [{ id: 'source-1' }],
      attachments: [{ artifactId: 'a-1', fileName: 'answer.txt' }],
    });
  });

  it('does not promote deltas or transport finals to a run result', () => {
    const state = replayRuntimeJournal([
      event(1, 'delta', { entity_type: 'run', entity_id: 'run-1', content: 'one ' }),
      event(2, 'delta', { entity_type: 'run', entity_id: 'run-1', content: 'two' }),
      event(3, 'final', { entity_type: 'run', entity_id: 'run-1', content: 'transport only' }),
      event(4, 'waiting_input', { entity_type: 'run', entity_id: 'run-1', question: 'Уточните запрос' }),
      event(5, 'budget_snapshot', { entity_type: 'run', entity_id: 'run-1', own: { llm_calls: 1 } }),
      event(6, 'error', { entity_type: 'run', entity_id: 'run-1', safe_message: 'Недоступно', traceback: 'secret' }),
    ]);
    expect(projectTraceRun(state)).toMatchObject({
      finalContent: '', status: 'error', error: 'Операция не выполнена.',
      pause: { kind: 'input', question: 'Уточните запрос' }, limits: { rows: [{ key: 'llm_calls', used: 1, label: 'Вызовы LLM' }] },
    });
  });

  it('keeps a completed synthesis answer visible when a later planner failure marks the run failed', () => {
    const state = replayRuntimeJournal([
      event(1, 'error', {
        entity_type: 'error', entity_id: 'error-1', parent_entity_type: 'run', parent_entity_id: 'run-1',
        error_code: 'planner_checkpoint_failed', safe_message: 'Не удалось применить повторный план',
      }),
      event(2, 'final_answer_marker', {
        entity_type: 'run', entity_id: 'run-1', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1',
        status: 'completed', content: 'Данные не получены, сводку составить не удалось.', sources: [],
        attachments: [{ artifact_id: 'artifact-1', file_name: 'report.txt' }],
      }),
      event(3, 'run_end', { entity_type: 'run', entity_id: 'run-1', status: 'failed' }),
    ]);

    expect(projectTraceRun(state)).toMatchObject({
      status: 'failed',
      finalContent: 'Данные не получены, сводку составить не удалось.',
      error: 'Операция не выполнена.',
      attachments: [{ artifactId: 'artifact-1', fileName: 'report.txt' }],
    });
  });
});


describe('executor memory snapshots', () => {
  it('keeps identity-only lookup terms without inventing definitions', () => {
    const memory = memoryContextFromPayload({ memory_context: { glossary: [{ term: 'SLO', aliases: ['target'] }] } });
    expect(memory.context).toEqual([{ type: 'glossary', scope: 'global', term: 'SLO', description: '', aliases: ['target'] }]);
  });

  it('renders real glossary definitions and preserves knowledge provenance', () => {
    const memory = memoryContextFromPayload({ memory_context: [{ type: 'memory_recall',
      resolved_terms: [{ term: 'SLO', definition: 'Service level objective', aliases: ['target'] }],
      durable_facts: [{ scope: 'tenant', subject: 'region', value: 'msk' }],
      applicable_rules: [{ id: 'rule-1', subject: 'deploy', kind: 'rule', content: { approval: true }, scope_keys: ['team.ops'], source_references: [{ document_id: 'doc-1' }] }],
    }] });
    expect(memory.context).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: 'glossary', description: 'Service level objective' }),
      expect.objectContaining({ type: 'knowledge', raw: expect.objectContaining({ id: 'rule-1', scope_keys: ['team.ops'] }) }),
    ]));
    expect(memory.selectedFacts).toBe(1);
    expect(memory.selectedMemoryItems).toBe(1);
  });

  it('attaches scoped inputs and successful memory reads to their owning planner only', () => {
    const state = replayRuntimeJournal([
      event(1, 'orchestrator_start', { entity_type: 'orchestrator', entity_id: 'planner', role: 'planner', context_snapshot: {
        inputs: { goal: 'посмотри в инвентори какие у меня есть коммутаторы', task_brief: { constraints: ['Проверить актуальное состояние'] } },
      } }),
      event(2, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner', iteration: 1 }),
      event(3, 'status', { entity_type: 'planner_iteration', entity_id: 'iteration-1', stage: 'memory_context_used', memory_context: [{ scope: 'user', subject: 'language', value: 'ru' }] }),
      event(4, 'tool_call', { entity_type: 'tool_call', entity_id: 'read-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', tool: 'memory.search', call_id: 'read-1' }),
      event(5, 'tool_result', { entity_type: 'tool_call', entity_id: 'read-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', tool: 'memory.search', call_id: 'read-1', success: true, data: { memory_context: { durable_facts: [{ scope: 'tenant', subject: 'region', value: 'msk' }] } } }),
    ]);
    const planner = projectTraceStages(state)[0].executorRuns[0];
    expect(planner.memoryContext?.context).toHaveLength(2);
    expect(planner.input).toEqual({ goal: 'посмотри в инвентори какие у меня есть коммутаторы', task_brief: { constraints: ['Проверить актуальное состояние'] } });
    expect(resolveTraceInspectionTarget(state, planner.inspectorKey)?.tabs.map((tab) => tab.id)).toEqual(expect.arrayContaining(['input', 'memory']));
    expect(memoryContextFromTool(planner.calls[0])?.context).toEqual([{ type: 'fact', scope: 'tenant', subject: 'region', value: 'msk' }]);
  });
});

describe('HippoRAG memory inspection', () => {
  it('shows native passages in tool response and secretary memory without a duplicate tool memory tab', () => {
    const items = [{ kind: 'document_passage', subject: 'Регламент', text: 'Перед работами согласовать окно.', score: 0.9,
      source_references: [{ document_id: 'doc-1', filename: 'reglament.md' }] }];
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1' }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'secretary-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'secretary' }),
      event(4, 'status', { entity_type: 'agent_execution', entity_id: 'secretary-1', stage: 'memory_context_used', memory_context: [{ scope: 'user', subject: 'language', value: 'ru' }] }),
      event(5, 'tool_call', { entity_type: 'tool_call', entity_id: 'memory-call', parent_entity_type: 'agent_execution', parent_entity_id: 'secretary-1', tool: 'memory.search', call_id: 'memory-call' }),
      event(6, 'tool_result', { entity_type: 'tool_call', entity_id: 'memory-call', parent_entity_type: 'agent_execution', parent_entity_id: 'secretary-1', tool: 'memory.search', success: true,
        data: { backend: 'hipporag', items, count: 1, memory_context: { type: 'memory_recall', relevant_knowledge: items } } }),
    ]);
    const secretary = projectTraceStages(state)[0].steps[0].executorRuns[0];
    expect(secretary.memoryContext?.selectedFacts).toBe(1);
    expect(secretary.memoryContext?.selectedMemoryItems).toBe(1);
    expect(secretary.memoryContext?.context).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: 'knowledge', value: items[0].text, sourceReferences: [expect.objectContaining({ filename: 'reglament.md' })] }),
    ]));
    const call = secretary.calls[0];
    expect(memoryContextFromTool(call)?.selectedMemoryItems).toBe(1);
    const target = resolveTraceInspectionTarget(state, call.entity.key);
    expect(target?.tabs.map(tab => tab.id)).toContain('response');
    expect(target?.tabs.map(tab => tab.id)).not.toContain('memory');
  });

  it('uses native source metadata when a passage has no subject', () => {
    const memory = memoryContextFromPayload({ memory_context: { items: [{ text: 'Сделать резервную копию',
      metadata: { filename: 'backup.md', source_refs: [{ document_id: 'doc-2' }] } }] } });
    expect(memory.context[0]).toMatchObject({ type: 'knowledge', subject: 'backup.md', value: 'Сделать резервную копию', sourceReferences: [{ document_id: 'doc-2' }] });
  });
});
