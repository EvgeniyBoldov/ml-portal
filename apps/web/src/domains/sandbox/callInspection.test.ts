import { describe, expect, it } from 'vitest';
import { callDisplayName, formatFieldLabel, llmOutcome, llmResponseContent, llmResponseStatus, parseCallContent, safeFailureMessage, sanitizeDisplay, toDisplayEntries, toolResult } from './callInspection';

describe('call inspection projection', () => {
  it('parses fenced tool calls into structured data', () => {
    expect(parseCallContent('```tool_call\n{"tool":"collection.template.fill","arguments":{"filename":"request.xlsx"}}\n```')).toMatchObject({
      kind: 'tool_call', data: { tool: 'collection.template.fill', arguments: { filename: 'request.xlsx' } },
    });
  });

  it('hides journal identifiers and storage/schema internals outside RAW', () => {
    expect(sanitizeDisplay({ row_id: 'uuid', artifact_id: 'uuid', source: 's3://private', template_schema: { fields: [] }, title: 'Шаблон' })).toEqual({ title: 'Шаблон' });
  });

  it('preserves domain payloads and references in semantic result data', () => {
    expect(sanitizeDisplay({ data: [{ item_id: 42, content: 'payload', source: 'registry', status: 'ready' }], metadata: { document_id: 7 } }))
      .toEqual({ data: [{ item_id: 42, content: 'payload', source: 'registry', status: 'ready' }], metadata: { document_id: 7 } });
  });

  it('uses safe tool outcome fields', () => {
    expect(toolResult({ result: { success: false, safe_message: 'Шаблон не готов', data: { row_id: 'uuid' } } })).toMatchObject({
      success: false, message: 'Операция не выполнена.', data: { row_id: 'uuid' }, diagnostic: { safe_message: 'Шаблон не готов' },
    });
    expect(callDisplayName('collection.template.get_schema', new Map([['collection.template.get_schema', 'Получить схему шаблона']]))).toBe('Получить схему шаблона');
    expect(callDisplayName('collection.template.get_schema')).toBe('collection · template · get_schema');
  });

  it('keeps contradictory explicit and nested tool outcomes unknown', () => {
    expect(toolResult({ success: true, result: { success: false, status: 'failed' } }))
      .toMatchObject({ success: undefined, message: 'Операция не выполнена.' });
    expect(toolResult({ status: 'completed', result: { status: 'failed' } }).success).toBeUndefined();
    expect(toolResult({ status: 'completed', mcp_failure: { version: 1, category: 'input' } }).success).toBeUndefined();
    expect(toolResult({ success: false, result: { success: false, status: 'failed' } }).success).toBe(false);
  });

  it('normalizes MCP v1 failures without surfacing backend diagnostics', () => {
    const technical = 'SQLAlchemy: SELECT secret FROM private_table';
    for (const payload of [
      { mcp_failure: { version: 1, category: 'input', code: 'missing_required_field', details: technical } },
      { result_envelope: { failure: { version: 1, category: 'input', code: 'missing_required_field', details: technical } } },
      { result: { failure: { version: 1, category: 'input', code: 'missing_required_field', details: technical } } },
    ]) {
      expect(toolResult(payload)).toMatchObject({
        success: false,
        message: 'Источник отклонил параметры запроса.',
        failure: { code: 'missing_required_field' },
      });
      expect(toolResult(payload).message).not.toContain(technical);
      expect(toolResult(payload).diagnostic).toEqual(expect.objectContaining({ details: technical }));
    }
  });

  it('keeps explicit result completeness and count metadata including zero and false', () => {
    expect(toolResult({ result_id: 'opaque', result_delivery: 'stored', result_inline_complete: false, result_source_complete: true, result_row_count: 0, result_source_total: 14 }))
      .toMatchObject({ resultId: 'opaque', delivery: 'stored', inlineComplete: false, sourceComplete: true, returnedCount: 0, sourceTotal: 14 });
  });

  it('preserves ordinary result objects and unwraps only recognized result pages or runtime descriptors', () => {
    const domain = { data: 'domain payload', other: 'must remain' };
    expect(toolResult({ success: true, data: domain }).data).toEqual(domain);
    expect(toolResult({ success: true, data: { value: [{ id: 2 }], meta: { row_count: 1 } } }).data).toEqual({ value: [{ id: 2 }], meta: { row_count: 1 } });
    expect(toolResult({ success: true, data: { rows: [{ id: 2 }], _runtime_result: { row_count: 1, inline_complete: true } } }).data).toEqual({ rows: [{ id: 2 }], _runtime_result: { row_count: 1, inline_complete: true } });
  });

  it('reads completeness from the canonical paged ResultPage metadata', () => {
    expect(toolResult({ success: true, data: { value: [], meta: { total: 0, complete: false, has_next: true } } }))
      .toMatchObject({ returnedCount: 0, sourceTotal: 0, sourceComplete: false });
    expect(toolResult({ success: true, data: { meta: { total: 0, complete: false } } }).sourceComplete).toBeUndefined();
  });

  it('does not display a stored result descriptor as if it contained the full dataset', () => {
    expect(toolResult({ result_delivery: 'stored', result_inline_complete: false, result_row_count: 8, data: { result_id: 'opaque', row_count: 8, sql_ref: 'private_table' } }))
      .toMatchObject({ data: { result_id: 'opaque', row_count: 8, sql_ref: 'private_table' }, returnedCount: 8, delivery: 'stored', inlineComplete: false });
  });

  it('recognizes strong legacy stored-result markers before semantic sanitization', () => {
    const raw = toolResult({ success: true, data: {
      result_id: 'legacy-result-id', sql_ref: 'private_result_table', payload_type: 'rows', row_count: 500,
      observed_schema: { secret: 'private schema' }, revision: 4, payload_chars: 15000, has_more: true,
    } });
    expect(raw).toMatchObject({ storedDescriptor: true, delivery: 'stored', resultId: 'legacy-result-id', returnedCount: 500 });
    expect(sanitizeDisplay(raw.data)).toEqual({ payload_type: 'rows', row_count: 500, observed_schema: { secret: 'private schema' }, revision: 4, payload_chars: 15000, has_more: true });
    expect(toolResult({ success: true, data: { result_id: 'domain-id', title: 'An issue' } }).storedDescriptor).toBe(false);
  });

  it('does not infer success from an empty legacy result', () => {
    expect(toolResult({ data: [] }).success).toBeUndefined();
    expect(toolResult({ success: true, mcp_failure: { version: 1, category: 'unknown', code: 'backend_error' } }).success).toBeUndefined();
  });

  it('maps only exact failure categories and runtime codes to user-facing text', () => {
    expect(safeFailureMessage('auth', undefined)).toBe('Сервис отклонил данные авторизации.');
    expect(safeFailureMessage('access', undefined)).toBe('У учётной записи нет доступа к запрошенным данным.');
    expect(safeFailureMessage('unknown', 'auth_required')).toBe('Операция не выполнена.');
    expect(safeFailureMessage('SQLAlchemyError', 'unknown_runtime_code')).toBe('Операция не выполнена.');
    expect(safeFailureMessage(undefined, 'budget_exceeded')).toBe('Лимит выполнения задачи исчерпан.');
    expect(safeFailureMessage(undefined, 'llm_timeout')).toBe('Модель не ответила вовремя.');
    expect(safeFailureMessage(undefined, 'llm_context_window_exceeded')).toBe('Запрос не помещается в доступный контекст модели.');
    expect(safeFailureMessage(undefined, 'turn_preflight_unavailable')).toBe('Не удалось проверить готовность и выбрать маршрут.');
  });

  it('maps only the exact known legacy search error and keeps the original diagnostic', () => {
    expect(toolResult({ success: false, safe_message: 'q is required' })).toMatchObject({
      message: 'Не задан поисковый запрос.',
      diagnostic: { safe_message: 'q is required' },
    });
    expect(toolResult({ success: false, safe_message: 'q is required; SQLAlchemy SELECT private_data' })).toMatchObject({
      message: 'Операция не выполнена.',
      diagnostic: { safe_message: 'q is required; SQLAlchemy SELECT private_data' },
    });
    expect(toolResult({ success: false, safe_message: 'SQLAlchemy UndefinedColumnError' }).message).toBe('Операция не выполнена.');
    expect(toolResult({ success: true, safe_message: 'q is required' }).message).toBeUndefined();
    expect(toolResult({ success: false, safe_message: 'q is required', mcp_failure: { version: 1, category: 'unknown' } }).message)
      .toBe('Операция не выполнена.');
  });

  it('preserves domain errors and details inside successful tool result data', () => {
    const result = toolResult({
      success: true,
      data: { details: { result: 'retained' }, errors: [{ object_type: 'device', status: 422, error: 'domain validation issue' }] },
    });
    expect(sanitizeDisplay(result.data)).toEqual({
      details: { result: 'retained' },
      errors: [{ object_type: 'device', status: 422, error: 'domain validation issue' }],
    });
  });

  it('keeps independently recorded received and stored counts separate', () => {
    const recorded = toolResult({ success: true, result_delivery: 'stored', result_id: 'r', result_row_count: 49, returned_count: 50, result_source_total: 72, data: { row_count: 49, payload_type: 'array' } });
    expect(recorded).toMatchObject({ returnedCount: 49, receivedCount: 50, sourceTotal: 72 });
    const legacy = toolResult({ success: true, result_delivery: 'stored', result_id: 'r', result_row_count: 50, result_source_total: 72, data: { row_count: 50, payload_type: 'array' } });
    expect(legacy.receivedCount).toBeUndefined();
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

  it('classifies strict iteration proposals without interpreting legacy actions', () => {
    expect(llmOutcome({ content: '' }, 2)).toEqual({ kind: 'tools', label: 'Вызов инструментов', count: 2 });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"terminal":"synthesis","tasks":[{},{}]}' })).toEqual({ kind: 'plan', label: 'Итерация', count: 2 });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"terminal":"planner","tasks":[{}]}' })).toEqual({ kind: 'plan', label: 'Следующая итерация', count: 1 });
    expect(llmOutcome({ purpose: 'tool_decision_or_answer', content: '{"terminal":"synthesis","tasks":[{"task_id":"fill"}]}' })).toEqual({ kind: 'answer', label: 'Ответ' });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"proposal":{"terminal":"synthesis","tasks":[{"task_id":"fill"}]}}' })).toEqual({ kind: 'answer', label: 'Ответ' });
    expect(llmOutcome({ purpose: 'tool_decision_or_answer', content: '{"tool":"file.read","arguments":{"artifact_id":"a"}}' })).toEqual({ kind: 'tools', label: 'Вызов инструментов', count: 1 });
    expect(llmOutcome({ purpose: 'planning_decision', content: '{"action":"complete"}' })).toEqual({ kind: 'answer', label: 'Ответ' });
    expect(llmOutcome({ content: '' })).toEqual({ kind: 'empty', label: 'Пусто' });
  });
});
