import { describe, expect, it } from 'vitest';
import { applyRuntimeJournalEvent, emptySandboxTrace } from './traceState';
import { projectTraceStages, resolveTraceInspectionTarget, stepFor } from './traceProjection';

const event = (sequence: number, type: string, entityType: string, entityId: string, parent?: [string, string]) => ({
  id: `event-${sequence}`, run_id: 'run-1', sequence, event_type: type,
  occurred_at: '2026-01-01T00:00:00Z', entity_type: entityType, entity_id: entityId,
  parent_entity_type: parent?.[0] ?? null, parent_entity_id: parent?.[1] ?? null,
  caused_by_event_id: null, duration_ms: null, payload: {},
});

describe('sandbox trace state', () => {
  it('creates and updates explicit entities without heuristics', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, event(3, 'llm_request', 'llm_call', 'call-1', ['planner_iteration', 'iteration-1']));
    state = applyRuntimeJournalEvent(state, event(4, 'llm_response', 'llm_call', 'call-1', ['planner_iteration', 'iteration-1']));

    expect(state.entitiesByKey['run:run-1'].childKeys).toEqual(['planner_iteration:iteration-1']);
    expect(state.entitiesByKey['llm_call:call-1'].eventIds).toEqual(['event-3', 'event-4']);
    expect(state.entitiesByKey['llm_call:call-1'].status).toBe('completed');
    expect(state.protocolError).toBeNull();
  });

  it('buffers an out-of-order live journal frame until its missing predecessor arrives', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']));
    expect(state.eventIdsBySequence).toEqual([]);
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));

    expect(state.eventIdsBySequence).toEqual(['event-1', 'event-2']);
    expect(state.pendingBySequence).toEqual({});
    expect(state.protocolError).toBeNull();
  });

  it('projects an iteration, executor and request-response calls in sequence order', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, {
      ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']),
      payload: { iteration: 1 },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']),
      payload: { title: 'Сформировать план' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(4, 'agent_start', 'agent_execution', 'planner-run', ['step', 'step-1']),
      payload: { task_title: 'Сформировать план', agent_slug: 'planner', executor_type: 'planner', executor_name: 'Планер' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(5, 'llm_request', 'llm_call', 'llm-1', ['agent_execution', 'planner-run']),
      payload: { model: 'qwen' },
    });
    state = applyRuntimeJournalEvent(state, event(6, 'llm_response', 'llm_call', 'llm-1', ['agent_execution', 'planner-run']));
    state = applyRuntimeJournalEvent(state, {
      ...event(7, 'tool_call', 'tool_call', 'tool-1', ['agent_execution', 'planner-run']),
      payload: { tool: 'file.read' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(8, 'tool_result', 'tool_call', 'tool-1', ['agent_execution', 'planner-run']),
      payload: { success: true },
    });

    const [stage] = projectTraceStages(state);
    expect(stage.number).toBe(1);
    expect(stage.executorRuns).toHaveLength(1);
    expect(stage.executorRuns[0].executorType).toBe('PLANNER');
    expect(stage.executorRuns[0].calls.map((call) => call.title)).toEqual(['qwen', 'file · read']);
    expect(stage.executorRuns[0].calls.every((call) => call.response)).toBe(true);
    expect(state.entitiesByKey['tool_call:tool-1'].status).toBe('completed');
  });

  it('marks a failed tool result as failed', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'tool_call', 'tool_call', 'tool-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, {
      ...event(3, 'tool_result', 'tool_call', 'tool-1', ['run', 'run-1']),
      payload: { success: false },
    });

    expect(state.entitiesByKey['tool_call:tool-1'].status).toBe('failed');
  });

  it('keeps extraction as a canonical child of its tool call', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']));
    state = applyRuntimeJournalEvent(state, { ...event(4, 'agent_start', 'agent_execution', 'agent-1', ['step', 'step-1']), payload: { agent_slug: 'reader' } });
    state = applyRuntimeJournalEvent(state, event(5, 'tool_call', 'tool_call', 'tool-1', ['agent_execution', 'agent-1']));
    state = applyRuntimeJournalEvent(state, event(6, 'extraction_started', 'extraction', 'extract-1', ['tool_call', 'tool-1']));
    state = applyRuntimeJournalEvent(state, event(7, 'extraction_completed', 'extraction', 'extract-1', ['tool_call', 'tool-1']));
    state = applyRuntimeJournalEvent(state, { ...event(8, 'tool_result', 'tool_call', 'tool-1', ['agent_execution', 'agent-1']), payload: { success: true } });

    const call = projectTraceStages(state)[0].executorRuns[0].calls[0];
    expect(call.extraction?.entity.key).toBe('extraction:extract-1');
    expect(call.extraction?.entity.status).toBe('completed');
  });

  it('does not turn a tool result without success into a success', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'tool_call', 'tool_call', 'tool-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, event(3, 'tool_result', 'tool_call', 'tool-1', ['run', 'run-1']));

    expect(state.entitiesByKey['tool_call:tool-1'].status).toBe('unknown');
  });

  it('marks LLM responses with an error type as failed', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'llm_request', 'llm_call', 'call-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, { ...event(3, 'llm_response', 'llm_call', 'call-1', ['run', 'run-1']), payload: { error_type: 'ProviderError' } });

    expect(state.entitiesByKey['llm_call:call-1'].status).toBe('failed');
  });

  it('marks error entities as errors', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'error', 'error', 'error-1', ['run', 'run-1']));

    expect(state.entitiesByKey['error:error-1'].status).toBe('error');
  });

  it('projects clarification, confirmation and errors as executor calls', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, {
      ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']),
      payload: { title: 'План' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(4, 'agent_start', 'agent_execution', 'planner-run', ['step', 'step-1']),
      payload: { agent_slug: 'planner', task_title: 'План' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(5, 'waiting_input', 'interaction', 'interaction-clarify', ['agent_execution', 'planner-run']),
      payload: { question: 'Какой проект?', interaction_kind: 'clarify', parent_entity_type: 'agent_execution', parent_entity_id: 'planner-run' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(6, 'confirmation_required', 'question_answer', 'interaction-1', ['agent_execution', 'planner-run']),
      payload: { message: 'Подтвердить запись?', parent_entity_type: 'agent_execution', parent_entity_id: 'planner-run' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(7, 'error', 'error', 'error-1', ['agent_execution', 'planner-run']),
      payload: { error: 'Ошибка инструмента' },
    });

    const calls = projectTraceStages(state)[0].executorRuns[0].calls;
    expect(calls.map((call) => call.kind)).toEqual(['clarify', 'confirm', 'error']);
    expect(calls.map((call) => call.title)).toEqual(['Какой проект?', 'Подтвердить запись?', 'Ошибка инструмента']);
  });

  it('projects the displayed step from the executor task snapshot', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, { ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']), payload: { iteration: 2 } });
    state = applyRuntimeJournalEvent(state, {
      ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']),
      payload: { task_id: 'collect', title: 'Собрать данные', objective: 'Получить инвентарь', inputs: { site: 'msk' } },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(4, 'agent_start', 'agent_execution', 'agent-1', ['step', 'step-1']),
      payload: { task_id: 'collect', task_title: 'Собрать данные', task_objective: 'Получить инвентарь', task_inputs: { site: 'msk' } },
    });

    expect(stepFor(projectTraceStages(state)[0])).toMatchObject({
      taskId: 'collect', title: 'Собрать данные', objective: 'Получить инвентарь', inputs: { site: 'msk' },
    });
  });

  it('uses the canonical step entity and reaches executors nested beneath it', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, { ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']), payload: { iteration: 1 } });
    state = applyRuntimeJournalEvent(state, {
      ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']),
      payload: { title: 'Собрать данные', objective: 'Получить инвентарь', inputs: { site: 'msk' } },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(4, 'agent_start', 'agent_execution', 'agent-1', ['step', 'step-1']),
      payload: { agent_slug: 'viewer', task_title: 'Собрать данные' },
    });

    const [stage] = projectTraceStages(state);
    expect(stage.executorRuns).toHaveLength(1);
    expect(stepFor(stage)).toMatchObject({ key: 'step:step-1', title: 'Собрать данные', objective: 'Получить инвентарь', inputs: { site: 'msk' } });
  });

  it('keeps every task step in one planner iteration', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, { ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']), payload: { iteration: 1, iteration_type: 'decision' } });
    state = applyRuntimeJournalEvent(state, { ...event(3, 'step_start', 'step', 'step-plan', ['planner_iteration', 'iteration-1']), payload: { step_number: 1, title: 'Сформировать план' } });
    state = applyRuntimeJournalEvent(state, { ...event(4, 'agent_start', 'agent_execution', 'planner-run', ['step', 'step-plan']), payload: { agent_slug: 'planner', task_title: 'Сформировать план' } });
    state = applyRuntimeJournalEvent(state, { ...event(5, 'step_start', 'step', 'step-network', ['planner_iteration', 'iteration-1']), payload: { step_number: 2, task_id: 'network', title: 'Проверить сеть' } });
    state = applyRuntimeJournalEvent(state, { ...event(6, 'agent_start', 'agent_execution', 'network-run', ['step', 'step-network']), payload: { agent_slug: 'net.engineer', task_title: 'Проверить сеть' } });
    state = applyRuntimeJournalEvent(state, { ...event(7, 'step_start', 'step', 'step-review', ['planner_iteration', 'iteration-1']), payload: { step_number: 3, task_id: 'review', title: 'Проверить результат' } });
    state = applyRuntimeJournalEvent(state, { ...event(8, 'agent_start', 'agent_execution', 'review-run', ['step', 'step-review']), payload: { agent_slug: 'viewer', task_title: 'Проверить результат' } });

    const [stage] = projectTraceStages(state);
    expect(stage.steps).toHaveLength(3);
    expect(stage.steps.map((step) => [step.number, step.title, step.executorRuns[0]?.executorSlug])).toEqual([
      [1, 'Сформировать план', 'planner'],
      [2, 'Проверить сеть', 'net.engineer'],
      [3, 'Проверить результат', 'viewer'],
    ]);
    expect(stage.steps.map((step) => step.entity.key)).toEqual(['step:step-plan', 'step:step-network', 'step:step-review']);
  });

  it('projects calls from the canonical executor parent link', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, { ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']), payload: { iteration: 1 } });
    state = applyRuntimeJournalEvent(state, { ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']), payload: { title: 'Выполнить задачу' } });
    state = applyRuntimeJournalEvent(state, { ...event(4, 'agent_start', 'agent_execution', 'agent-1', ['step', 'step-1']), payload: { agent_slug: 'worker', task_title: 'Выполнить задачу' } });
    state = applyRuntimeJournalEvent(state, { ...event(5, 'llm_request', 'llm_call', 'llm-1', ['agent_execution', 'agent-1']), payload: { model: 'qwen' } });
    state = applyRuntimeJournalEvent(state, { ...event(6, 'llm_response', 'llm_call', 'llm-1', ['agent_execution', 'agent-1']), payload: { model: 'qwen' } });

    const [stage] = projectTraceStages(state);
    expect(stage.executorRuns[0].calls.map((call) => call.title)).toEqual(['qwen']);
  });

  it('keeps timeout retries and an unfinished call visible as an incomplete execution', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, { ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']), payload: { iteration: 1, iteration_type: 'decision' } });
    state = applyRuntimeJournalEvent(state, { ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']), payload: { title: 'Сформировать план' } });
    state = applyRuntimeJournalEvent(state, { ...event(4, 'agent_start', 'agent_execution', 'planner-run', ['step', 'step-1']), payload: { agent_slug: 'planner', task_title: 'Сформировать план' } });
    state = applyRuntimeJournalEvent(state, { ...event(5, 'llm_request', 'llm_call', 'llm-1', ['agent_execution', 'planner-run']), payload: { model: 'gemma', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(6, 'llm_response', 'llm_call', 'llm-1', ['agent_execution', 'planner-run']), payload: { error_type: 'TimeoutError', error_code: 'llm_timeout', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(7, 'protocol_retry', 'llm_call', 'llm-1', ['agent_execution', 'planner-run']), payload: { reason: 'timeout', attempt: 1, llm_call_id: 'llm-1', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(8, 'llm_request', 'llm_call', 'llm-2', ['agent_execution', 'planner-run']), payload: { model: 'gemma', logical_llm_call_id: 'logical-1' } });

    const [stage] = projectTraceStages(state);
    const executor = stage.executorRuns[0];
    expect(executor.entity.status).toBe('running');
    expect(executor.metrics).toMatchObject({ calls: 1, failedCalls: 0, retries: 1 });
    expect(executor.calls[0].attempts).toHaveLength(2);
    expect(executor.calls[0].response).toBeUndefined();
    expect(executor.calls[0].retryEvents.map((item) => item.event_type)).toEqual(['protocol_retry']);
    expect(executor.calls[0].events.map((item) => item.id)).toHaveLength(3);
    expect(resolveTraceInspectionTarget(state, executor.calls[0].entity.key)).toMatchObject({ kind: 'call' });
  });

  it('keeps a native-tool fallback and plaintext retry under one LLM call id', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, { ...event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']), payload: { iteration: 1 } });
    state = applyRuntimeJournalEvent(state, { ...event(3, 'step_start', 'step', 'step-1', ['planner_iteration', 'iteration-1']), payload: { title: 'Выполнить задачу' } });
    state = applyRuntimeJournalEvent(state, { ...event(4, 'agent_start', 'agent_execution', 'agent-1', ['step', 'step-1']), payload: { agent_slug: 'worker' } });
    state = applyRuntimeJournalEvent(state, { ...event(5, 'llm_request', 'llm_call', 'llm-native', ['agent_execution', 'agent-1']), payload: { model: 'qwen', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(6, 'llm_response', 'llm_call', 'llm-native', ['agent_execution', 'agent-1']), payload: { error_type: 'LLMToolCallingUnsupportedError', error_code: 'llm_tool_calling_unsupported', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(7, 'protocol_retry', 'llm_call', 'llm-native', ['agent_execution', 'agent-1']), payload: { reason: 'native_tool_calling_unsupported', llm_call_id: 'llm-native', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(8, 'llm_request', 'llm_call', 'llm-native', ['agent_execution', 'agent-1']), payload: { model: 'qwen', logical_llm_call_id: 'logical-1' } });
    state = applyRuntimeJournalEvent(state, { ...event(9, 'llm_response', 'llm_call', 'llm-native', ['agent_execution', 'agent-1']), payload: { logical_llm_call_id: 'logical-1', content: 'готово' } });

    const executor = projectTraceStages(state)[0].executorRuns[0];
    expect(executor.entity.status).not.toBe('running');
    expect(executor.calls).toHaveLength(1);
    expect(executor.calls[0]).toMatchObject({ logicalLlmCallId: 'logical-1' });
    expect(executor.calls[0].entity.id).toBe('llm-native');
    expect(executor.calls[0].events).toHaveLength(5);
    expect(executor.calls[0].retryEvents).toHaveLength(1);
    expect(executor.calls[0].response?.payload.content).toBe('готово');
  });
});
