import { describe, expect, it } from 'vitest';

import { projectTraceStages, resolveTraceInspectionTarget, stepFor } from './traceProjection';
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

describe('projectTraceStages memory components', () => {
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
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Задача', 'Изменения', 'Prompt', 'RBAC', 'Лимиты', 'Preflight', 'RAW']);
    expect(compactor.memoryResult?.facts).toEqual([expect.objectContaining({
      subject: 'network.zone',
      changeType: 'candidate_confirmed',
      statusBefore: 'pending',
      statusAfter: 'confirmed',
      supportDelta: 1,
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
    expect(executor.preflight).toMatchObject({
      mode: 'partial', durationMs: 12, operationsCount: 4, dataInstancesCount: 2,
      missing: { tools: [], collections: ['private_docs (rbac_denied)'], credentials: ['dcbox'] },
    });
  });

  it('keeps a planner plan scoped to its own revision and maps planned tasks to steps', () => {
    const state = replayRuntimeJournal([
      event(1, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-1', iteration_number: 1 }),
      event(2, 'step_start', { entity_type: 'step', entity_id: 'step-1', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-1', task_id: 'plan-1', title: 'Сформировать план' }),
      event(3, 'agent_start', { entity_type: 'agent_execution', entity_id: 'planner-1', parent_entity_type: 'step', parent_entity_id: 'step-1', agent_slug: 'planner', task_title: 'Сформировать план' }),
      event(4, 'plan_created', {
        entity_type: 'plan', entity_id: 'plan-1', parent_entity_type: 'agent_execution', parent_entity_id: 'planner-1',
        revision_after: 1, patch: { decision: 'create_plan', tasks: [{ task_id: 'plan-1', executor: 'tech_fact_manager', intent: 'search_fact', instructions: 'Найти определение' }] },
      }),
      event(5, 'planner_iteration_start', { entity_type: 'planner_iteration', entity_id: 'iteration-2', iteration_number: 2 }),
      event(6, 'step_start', { entity_type: 'step', entity_id: 'step-2', parent_entity_type: 'planner_iteration', parent_entity_id: 'iteration-2', task_id: 'plan-2', title: 'Перепланировать' }),
      event(7, 'agent_start', { entity_type: 'agent_execution', entity_id: 'planner-2', parent_entity_type: 'step', parent_entity_id: 'step-2', agent_slug: 'planner', task_title: 'Перепланировать' }),
      event(8, 'plan_created', {
        entity_type: 'plan', entity_id: 'plan-2', parent_entity_type: 'agent_execution', parent_entity_id: 'planner-2',
        revision_after: 2, patch: { decision: 'revise_plan', tasks: [{ task_id: 'plan-2', executor: 'other_answer', intent: 'answer', instructions: 'Сформировать ответ' }] },
      }),
    ]);

    const [first, second] = projectTraceStages(state);
    const stageTarget = resolveTraceInspectionTarget(state, 'planner_iteration:iteration-1');
    const plannerTarget = resolveTraceInspectionTarget(state, first.executorRuns[0].inspectorKey);
    expect(first.kind).toBe('plan_revision');
    expect(first.steps[0].kind).toBe('planner_decision');
    expect(stageTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'План', 'Итоги', 'RAW']);
    expect(plannerTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'План', 'Prompt', 'RBAC', 'Лимиты', 'Preflight', 'RAW']);
    expect(first.plan?.tasks.map((task) => task.taskId)).toEqual(['plan-1']);
    expect(second.plan?.tasks.map((task) => task.taskId)).toEqual(['plan-2']);
    expect(first.steps[0].taskPresentation).toMatchObject({ taskId: 'plan-1', executor: 'tech_fact_manager', intent: 'search_fact' });
    expect(first.executorRuns[0].taskPresentation).toMatchObject({ taskId: 'planner-1', executor: 'planner', title: 'Сформировать план' });
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
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Задача', 'Memory', 'Prompt', 'RBAC', 'Лимиты', 'Preflight', 'RAW']);
    expect(stage.steps[0].taskPresentation).toMatchObject({ title: 'Отбор контекста', executor: 'memory_preparation' });
    expect(stage.executorRuns[0].memoryContext).toEqual({
      fallback: true,
      selectedFacts: 2,
      selectedProjects: 1,
      context: [{ type: 'fact', subject: 'role', value: 'engineer' }],
      ambiguities: ['СРК может означать несколько терминов'],
    });
  });

  it('uses synthesis presentation kinds and the shared executor tab policy', () => {
    const state = replayRuntimeJournal([
      event(1, 'synthesis_start', { entity_type: 'synthesis_run', entity_id: 'synthesis-1' }),
      event(2, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'synthesis_run', parent_entity_id: 'synthesis-1', purpose: 'final_answer' }),
    ]);

    const stage = projectTraceStages(state)[0];
    const target = resolveTraceInspectionTarget(state, 'synthesis_run:synthesis-1');
    const executorTarget = resolveTraceInspectionTarget(state, 'executor:synthesis_run:synthesis-1');
    const callTarget = resolveTraceInspectionTarget(state, 'llm_call:llm-1');
    expect(stage.kind).toBe('synthesis');
    expect(stepFor(stage).kind).toBe('synthesis');
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Итоги', 'RAW']);
    expect(executorTarget?.kind).toBe('executor');
    expect(executorTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Результат', 'Prompt', 'RBAC', 'Лимиты', 'Preflight', 'RAW']);
    expect(callTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Запрос', 'Результат', 'RAW']);
  });
});
