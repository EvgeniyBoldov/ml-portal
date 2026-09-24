import { describe, expect, it } from 'vitest';

import { projectTraceRun, projectTraceStages, resolveTraceInspectionTarget, stepFor } from './traceProjection';
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
      event(4, 'orchestrator_end', { entity_type: 'orchestrator', entity_id: 'preflight-1', role: 'turn_preflight', status: 'planner' }),
    ]);

    const executor = projectTraceStages(state).find((stage) => stage.kind === 'turn_preflight')?.executorRuns[0];
    expect(executor?.route).toEqual(expect.objectContaining({
      route: 'planner', goal: 'Сохранить факт', direction: 'В память пользователя', expectedResult: 'Факт сохранён',
      entityHints: ['НОП'], constraints: ['не выдумывать'],
      input: { user_request: 'Запомни факт', mechanical_lookup: { entities: ['НОП'] } },
    }));
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
    ];
    for (const events of [base, [...base, event(4, 'rbac_snapshot', {
      entity_type: 'planner_iteration', entity_id: 'iteration-1', parent_entity_type: 'orchestrator', parent_entity_id: 'planner-1', rbac: audit,
    })]]) {
      const state = replayRuntimeJournal(events);
      const planner = projectTraceStages(state)[0].executorRuns[0];
      const target = resolveTraceInspectionTarget(state, planner.inspectorKey);
      expect(target?.tabs.map((item) => item.label)).toContain('Доступ');
      expect(planner.access?.rows).toContainEqual({ kind: 'Агент', name: 'viewer', allowed: true, reason: 'Разрешён эффективной политикой' });
      expect(planner.access?.rows).toContainEqual({ kind: 'Агент', name: 'hidden', allowed: false, reason: 'Запрещён RBAC' });
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
    expect(target?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Результат', 'RAW']);
    expect(executorTarget?.kind).toBe('executor');
    expect(executorTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Результат', 'RAW']);
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
        summary: 'Получено: 2',
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
      event(5, 'budget_snapshot', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', own: { llm_calls: 1 }, limits: { llm_calls: 2 } }),
      event(6, 'preflight_started', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1' }),
      event(7, 'preflight_completed', { entity_type: 'preflight', entity_id: 'preflight-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', status: 'ok', missing: { tools: [], collections: [], credentials: [] } }),
      event(8, 'llm_request', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', messages: [{ role: 'system', content: 'prompt' }] }),
      event(9, 'llm_response', { entity_type: 'llm_call', entity_id: 'llm-1', parent_entity_type: 'agent_execution', parent_entity_id: 'agent-1', content: 'ok', status: 'completed' }),
      event(10, 'agent_end', { entity_type: 'agent_execution', entity_id: 'agent-1', parent_entity_type: 'step', parent_entity_id: 'step-1', status: 'completed', summary: 'Готово' }),
    ]);
    const stages = projectTraceStages(state);
    const executorTarget = resolveTraceInspectionTarget(state, 'agent_execution:agent-1');
    const callTarget = resolveTraceInspectionTarget(state, 'llm_call:llm-1');
    expect(executorTarget?.tabs.map((item) => item.label)).toEqual(['Инфо', 'Задача', 'Результат', 'Промпт', 'Доступ', 'Лимиты', 'Проверка', 'RAW']);
    if (executorTarget?.kind === 'executor') {
      expect(executorTarget.executor.access?.rows).toContainEqual({ kind: 'Агент', name: 'worker', allowed: true, reason: 'RBAC passed' });
      expect(executorTarget.executor.access?.rows).toContainEqual({ kind: 'Коллекция', name: 'docs', allowed: true, reason: 'Доступна выбранному агенту' });
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
    expect(target?.tabs.map((item) => item.label)).toContain('Инфо');
    expect(target?.tabs.map((item) => item.label)).not.toContain('Доступ');
    expect(target?.kind).toBe('executor');
    if (target?.kind === 'executor') expect(target.executor.access).toBeUndefined();
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
      expect.objectContaining({ key: 'tokens_total', value: 150, input: 100, output: 50, limit: expect.objectContaining({ limit: 200 }) }),
      expect.objectContaining({ key: 'llm_retries', value: 1 }),
      expect.objectContaining({ key: 'tool_errors', value: 1 }),
    ]));
    expect(executor.limits?.rows.map((row) => row.key)).toEqual(['llm_calls', 'tokens_total']);
  });
});

describe('projectTraceRun', () => {
  it('prefers the terminal answer and normalizes/deduplicates attachments', () => {
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
    ]);
    expect(projectTraceRun(state)).toMatchObject({
      runId: 'run-1', status: 'completed', finalContent: 'Готово',
      attachments: [{ artifactId: 'a-1', fileName: 'answer.txt' }],
    });
  });

  it('falls back to deltas and projects waiting/error/budget state safely', () => {
    const state = replayRuntimeJournal([
      event(1, 'delta', { entity_type: 'run', entity_id: 'run-1', content: 'one ' }),
      event(2, 'delta', { entity_type: 'run', entity_id: 'run-1', content: 'two' }),
      event(3, 'waiting_input', { entity_type: 'run', entity_id: 'run-1', question: 'Уточните запрос' }),
      event(4, 'budget_snapshot', { entity_type: 'run', entity_id: 'run-1', own: { llm_calls: 1 } }),
      event(5, 'error', { entity_type: 'run', entity_id: 'run-1', safe_message: 'Недоступно', traceback: 'secret' }),
    ]);
    expect(projectTraceRun(state)).toMatchObject({
      finalContent: 'one two', status: 'error', error: 'Недоступно',
      pause: { kind: 'input', question: 'Уточните запрос' }, limits: { rows: [{ key: 'llm_calls', used: 1, label: 'Вызовы LLM' }] },
    });
  });
});
