import { describe, expect, it } from 'vitest';
import { applyRuntimeJournalEvent, emptySandboxTrace } from './traceState';
import { projectTraceStages, stepFor } from './traceProjection';

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
      ...event(3, 'agent_start', 'agent_run', 'planner-run', ['planner_iteration', 'iteration-1']),
      payload: { task_title: 'Сформировать план', agent_slug: 'planner', executor_type: 'planner', executor_name: 'Планер' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(4, 'llm_request', 'llm_call', 'llm-1', ['agent_run', 'planner-run']),
      payload: { model: 'qwen' },
    });
    state = applyRuntimeJournalEvent(state, event(5, 'llm_response', 'llm_call', 'llm-1', ['agent_run', 'planner-run']));
    state = applyRuntimeJournalEvent(state, {
      ...event(6, 'tool_call', 'tool_call', 'tool-1', ['agent_run', 'planner-run']),
      payload: { tool: 'file.read' },
    });
    state = applyRuntimeJournalEvent(state, event(7, 'tool_result', 'tool_call', 'tool-1', ['agent_run', 'planner-run']));

    const [stage] = projectTraceStages(state);
    expect(stage.number).toBe(1);
    expect(stage.executorRuns).toHaveLength(1);
    expect(stage.executorRuns[0].executorType).toBe('PLANNER');
    expect(stage.executorRuns[0].calls.map((call) => call.title)).toEqual(['qwen', 'file.read']);
    expect(stage.executorRuns[0].calls.every((call) => call.response)).toBe(true);
  });

  it('projects clarification, confirmation and errors as executor calls', () => {
    let state = emptySandboxTrace();
    state = applyRuntimeJournalEvent(state, event(1, 'run_start', 'run', 'run-1'));
    state = applyRuntimeJournalEvent(state, event(2, 'planner_iteration_start', 'planner_iteration', 'iteration-1', ['run', 'run-1']));
    state = applyRuntimeJournalEvent(state, {
      ...event(3, 'agent_start', 'agent_run', 'planner-run', ['planner_iteration', 'iteration-1']),
      payload: { agent_slug: 'planner', task_title: 'План' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(4, 'planner_step', 'planner_step', 'step-1', ['planner_iteration', 'iteration-1']),
      payload: { kind: 'clarify', question: 'Какой проект?', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(5, 'confirmation_required', 'question_answer', 'interaction-1', ['agent_run', 'planner-run']),
      payload: { message: 'Подтвердить запись?', parent_entity_type: 'agent_run', parent_entity_id: 'planner-run' },
    });
    state = applyRuntimeJournalEvent(state, {
      ...event(6, 'error', 'error', 'error-1', ['agent_run', 'planner-run']),
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
      ...event(3, 'agent_start', 'agent_run', 'agent-1', ['planner_iteration', 'iteration-1']),
      payload: { task_id: 'collect', task_title: 'Собрать данные', task_objective: 'Получить инвентарь', task_inputs: { site: 'msk' } },
    });

    expect(stepFor(projectTraceStages(state)[0])).toMatchObject({
      taskId: 'collect', title: 'Собрать данные', objective: 'Получить инвентарь', inputs: { site: 'msk' },
    });
  });
});
