import { describe, expect, it } from 'vitest';
import { buildRunTrace, normalizeTraceEvent } from './normalize';

describe('runtimeTrace normalize', () => {
  it('maps known event to semantic category and title', () => {
    const event = normalizeTraceEvent({
      id: '1',
      raw_type: 'operation_call',
      data: { operation_slug: 'collection.document.search', arguments: { query: 'x' }, step: 2 },
    });

    expect(event.category).toBe('operation');
    expect(event.title).toBe('Вызов операции');
    expect(event.iteration).toBe(2);
    expect(event.inputs).toEqual({ arguments: { query: 'x' } });
  });

  it('maps retry and error statuses', () => {
    const retry = normalizeTraceEvent({
      id: '2',
      raw_type: 'protocol_retry',
      data: { reason: 'no_operation_call_before_answer' },
    });
    const failedOp = normalizeTraceEvent({
      id: '3',
      raw_type: 'operation_result',
      data: { success: false, operation_slug: 'x' },
    });

    expect(retry.category).toBe('retry');
    expect(retry.status).toBe('warn');
    expect(failedOp.status).toBe('error');
  });

  it('groups events by iteration', () => {
    const trace = buildRunTrace([
      { id: 'a', raw_type: 'user_request', data: { content: 'hello', step: 0 }, step_number: 0 },
      { id: 'b', raw_type: 'llm_call', data: { step: 1, response_length: 120 }, step_number: 1 },
      { id: 'c', raw_type: 'operation_call', data: { step: 1, operation_slug: 'search' }, step_number: 2 },
    ]);

    expect(trace.total_events).toBe(3);
    expect(trace.iterations).toHaveLength(2);
    expect(trace.iterations[1].events).toHaveLength(2);
  });

  it('falls back unknown types to unknown category (not system)', () => {
    const event = normalizeTraceEvent({
      id: 'z',
      raw_type: 'brand_new_event',
      data: { a: 1 },
    });

    expect(event.category).toBe('unknown');
    expect(event.title).toContain('brand_new_event');
  });

  it('recognizes system-like events by pattern', () => {
    const statusEvent = normalizeTraceEvent({
      id: 's1',
      raw_type: 'custom_status_event',
      data: {},
    });
    expect(statusEvent.category).toBe('system');

    const unknownEvent = normalizeTraceEvent({
      id: 'u1',
      raw_type: 'completely_unknown_xyz',
      data: {},
    });
    expect(unknownEvent.category).toBe('unknown');
  });

  it('maps llm_request payload into semantic inputs', () => {
    const event = normalizeTraceEvent({
      id: 'llm-req',
      raw_type: 'llm_request',
      data: {
        model: 'gpt-x',
        messages_sent: [{ role: 'system', content: 'prompt' }],
        request_payload: { goal: 'Find collections' },
      },
    });

    expect(event.category).toBe('llm');
    expect(event.inputs).toEqual({
      messages: [{ role: 'system', content: 'prompt' }],
      payload: { goal: 'Find collections' },
      model: 'gpt-x',
    });
    expect(event.summary).toBe('model=gpt-x');
  });

  it('summarizes planner events with kind and rationale', () => {
    const event = normalizeTraceEvent({
      id: 'planner-1',
      raw_type: 'planner_decision',
      data: { kind: 'call_agent', rationale: 'Need network inventory' },
    });
    expect(event.category).toBe('planner');
    expect(event.summary).toBe('call_agent: Need network inventory');
  });

  it('recognizes thinking planner steps and selected summary', () => {
    const event = normalizeTraceEvent({
      id: 'planner-thinking',
      raw_type: 'planner_decision',
      data: {
        kind: 'thinking',
        hypotheses: [{ summary: 'Use analyst', rationale: 'Best fit', risks: ['latency'] }],
        selected_hypothesis_index: 0,
        selected_action_kind: 'call_agent',
        selected_action_summary: 'Delegate to analyst first',
        selection_rationale: 'Need facts before finalizing',
      },
    });

    expect(event.category).toBe('planner');
    expect(event.summary).toBe('Delegate to analyst first');
  });

  it('summarizes question-answer interaction events', () => {
    const event = normalizeTraceEvent({
      id: 'qa-1',
      raw_type: 'question_answer',
      data: { question: 'Какой регламент?', user_answer: 'HR' },
    });

    expect(event.category).toBe('system');
    expect(event.title).toBe('Вопрос-ответ');
    expect(event.summary).toBe('Какой регламент? → HR');
  });

  it('keeps waiting_input as a readable interaction request', () => {
    const event = normalizeTraceEvent({
      id: 'wait-1',
      raw_type: 'waiting_input',
      data: { question: 'Укажите VLAN', reason: 'waiting_input' },
    });

    expect(event.title).toBe('Запрос уточнения');
    expect(event.summary).toBe('Укажите VLAN');
    expect(event.inputs).toEqual({
      question: 'Укажите VLAN',
      action: undefined,
      context: undefined,
    });
  });

  it('maps planner thinking llm turns to reasoning title and summary', () => {
    const event = normalizeTraceEvent({
      id: 'llm-thinking',
      raw_type: 'llm_turn',
      data: {
        purpose: 'planning_decision',
        model: 'gpt-5',
        parsed_response: {
          hypotheses: [{ summary: 'Use analyst' }],
          selected_action_summary: 'Сначала собрать факты',
        },
      },
    });

    expect(event.title).toBe('Рассуждение');
    expect(event.summary).toBe('Сначала собрать факты');
  });

  it('maps planner next-step llm turns to dedicated label', () => {
    const event = normalizeTraceEvent({
      id: 'llm-next-step',
      raw_type: 'llm_turn',
      data: { purpose: 'planning_decision', content: '{"kind":"call_agent","agent_slug":"analyst"}' },
    });

    expect(event.title).toBe('Следующий шаг');
    expect(event.summary).toBe('Следующий шаг');
  });

  it('maps tool protocol llm turns to dedicated label', () => {
    const event = normalizeTraceEvent({
      id: 'llm-tool-protocol',
      raw_type: 'llm_turn',
      data: { purpose: 'tool_decision_or_answer', content: '```operation_call\n{"tool":"search"}\n```' },
    });

    expect(event.title).toBe('Протокол инструмента');
    expect(event.summary).toBe('Протокол инструмента');
  });

  it('labels contract runtime errors explicitly', () => {
    const event = normalizeTraceEvent({
      id: 'runtime-error',
      raw_type: 'error',
      data: {
        error: 'Agent repeatedly skipped required operation calls',
        error_code: 'agent_required_operation_call_missing',
        _envelope: { phase: 'agent' },
      },
    });

    expect(event.title).toBe('Нарушение контракта агента');
    expect(event.summary).toBe('Agent repeatedly skipped required operation calls');
  });
});
