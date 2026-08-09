import { describe, expect, it } from 'vitest';
import { callDisplayName, formatFieldLabel, llmOutcome, llmResponseContent, llmResponseStatus, parseCallContent, sanitizeDisplay, toDisplayEntries, toolResult } from './callInspection';

describe('call inspection projection', () => {
  it('parses fenced tool calls into structured data', () => {
    expect(parseCallContent('```tool_call\n{"tool":"collection.template.fill","arguments":{"filename":"request.xlsx"}}\n```')).toMatchObject({
      kind: 'tool_call', data: { tool: 'collection.template.fill', arguments: { filename: 'request.xlsx' } },
    });
  });

  it('hides journal identifiers and storage/schema internals outside RAW', () => {
    expect(sanitizeDisplay({ row_id: 'uuid', artifact_id: 'uuid', source: 's3://private', template_schema: { fields: [] }, title: 'Шаблон' })).toEqual({ title: 'Шаблон' });
  });

  it('uses safe tool outcome fields', () => {
    expect(toolResult({ result: { success: false, safe_message: 'Шаблон не готов', data: { row_id: 'uuid' } } })).toMatchObject({
      success: false, message: 'Шаблон не готов', data: { row_id: 'uuid' },
    });
    expect(callDisplayName('collection.template.get_schema', new Map([['collection.template.get_schema', 'Получить схему шаблона']]))).toBe('Получить схему шаблона');
    expect(callDisplayName('collection.template.get_schema')).toBe('collection · template · get_schema');
  });

  it('keeps operator-facing fields while hiding call implementation metadata', () => {
    expect(toDisplayEntries({ agent_slug: 'planner', response_length: 42, model: 'qwen', tokens_total: 12 }))
      .toEqual([{ label: 'Модель', value: 'qwen' }, { label: 'Всего токенов', value: 12 }]);
  });

  it('formats unknown field keys consistently for inspector labels', () => {
    expect(formatFieldLabel('retryAfterMs')).toBe('Retry After Ms');
    expect(formatFieldLabel('provider.error_code')).toBe('Provider error code');
    expect(formatFieldLabel('status_code')).toBe('HTTP-статус');
  });

  it('renders a tool outcome as a status label rather than a boolean', () => {
    expect(toolResult({ success: false, safe_message: 'Недоступно' }).details)
      .toContainEqual({ label: 'Статус', value: 'Ошибка' });
  });

  it('uses the first non-empty LLM response variant', () => {
    expect(llmResponseContent({ parsed_response: {}, response: '{"answer":"ok"}', content: 'ignored' })).toBe('{"answer":"ok"}');
    expect(llmResponseStatus({ parsed_response: {}, response: '' })).toBe('empty');
    expect(llmResponseStatus({ content: 'answer', error_type: 'ProviderError' })).toBe('error');
  });

  it('classifies LLM outcomes by returned action instead of text presence', () => {
    expect(llmOutcome({ content: '' }, 2)).toEqual({ kind: 'tools', label: 'Вызов инструментов', count: 2 });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"action":"apply_graph","tasks":[{},{}]}' })).toEqual({ kind: 'plan', label: 'План', count: 2 });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"action":"revise_plan","tasks":[{}]}' })).toEqual({ kind: 'plan', label: 'Корректировка плана', count: 1 });
    expect(llmOutcome({ purpose: 'tool_decision_or_answer', content: '{"action":"apply_graph","tasks":[{"task_id":"fill"}]}' })).toEqual({ kind: 'plan', label: 'План', count: 1 });
    expect(llmOutcome({ purpose: 'tool_decision_or_answer', content: '{"plan":{"tasks":[{"task_id":"fill"}]}}' })).toEqual({ kind: 'plan', label: 'План', count: 1 });
    expect(llmOutcome({ purpose: 'tool_decision_or_answer', content: '{"tool":"file.read","arguments":{"artifact_id":"a"}}' })).toEqual({ kind: 'tools', label: 'Вызов инструментов', count: 1 });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"action":"ask_user"}' })).toEqual({ kind: 'clarify', label: 'Уточнение' });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"action":"complete"}' })).toEqual({ kind: 'complete', label: 'Ответ' });
    expect(llmOutcome({ content: '' })).toEqual({ kind: 'empty', label: 'Пусто' });
  });
});
