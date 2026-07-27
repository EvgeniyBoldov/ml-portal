import type { RuntimeJournalEvent } from './traceState';

export type DisplayEntry = { label: string; value: unknown };
export type ParsedContent = { text?: string; data?: unknown; kind: 'text' | 'json' | 'tool_call' };
export type ToolNameMap = ReadonlyMap<string, string>;

const HIDDEN_KEYS = new Set([
  '_envelope', 'entity_id', 'entity_type', 'parent_entity_id', 'parent_entity_type',
  'actor_entity_id', 'actor_type', 'agent_execution_id', 'call_id', 'llm_call_id',
  'planner_iteration_id', 'planner_run_id', 'run_id', 'chat_id', 'storage_uri', 'source',
  'debug', 'traceback', 'messages', 'content', 'parsed_response', 'response', 'data', 'result',
  'template_schema', 'runtime_schema', 'schema', 'locator', 'artifact_id',
  '_progress', 'agent_slug', 'structured_input', 'step_kind', 'native_tool_calling',
  'response_length', 'reused_from_call_id', 'sources', 'user_message', 'operator_message',
]);

const LABELS: Record<string, string> = {
  model: 'Модель', purpose: 'Назначение', temperature: 'Температура', max_tokens: 'Лимит токенов',
  native_tool_calling: 'Native tool calling', response_length: 'Размер ответа', tokens_in: 'Токены входа',
  tokens_out: 'Токены выхода', tokens_total: 'Всего токенов', duration_ms: 'Длительность',
  success: 'Статус', reused: 'Переиспользован', truncated: 'Сокращён', tool: 'Операция',
  operation_slug: 'Операция', safe_message: 'Сообщение', error_code: 'Код ошибки',
  retryable: 'Можно повторить', recoverable: 'Восстанавливаемая', title: 'Название',
  description: 'Описание', total: 'Всего', field_count: 'Полей', template_version: 'Версия',
  contract_version: 'Версия контракта', status: 'Статус', filename: 'Имя файла', limit: 'Лимит',
  query: 'Запрос', score: 'Релевантность', collection: 'Коллекция', purpose_label: 'Назначение',
};

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
);

export function callDisplayName(tool: string, names?: ToolNameMap): string {
  return names?.get(tool) ?? (tool ? tool.split('.').join(' · ') : 'Операция');
}

export function purposeLabel(purpose: unknown): string {
  const value = String(purpose ?? '');
  return ({ planning_decision: 'Принятие решения по плану', tool_decision_or_answer: 'Выбор действия или ответ', final_answer: 'Финальный ответ' } as Record<string, string>)[value] ?? (value || '—');
}

export function toDisplayEntries(value: unknown): DisplayEntry[] {
  return Object.entries(asRecord(value))
    .filter(([key, raw]) => !HIDDEN_KEYS.has(key) && !key.endsWith('_id') && raw !== null && raw !== undefined && raw !== '')
    .map(([key, raw]) => ({
      label: LABELS[key] ?? key.split('_').join(' '),
      value: key === 'purpose' ? purposeLabel(raw) : key === 'tool' || key === 'operation_slug' ? callDisplayName(String(raw)) : sanitizeDisplay(raw),
    }));
}

export function sanitizeDisplay(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeDisplay);
  const source = asRecord(value);
  if (Object.keys(source).length === 0) return value;
  return Object.fromEntries(Object.entries(source)
    .filter(([key]) => !HIDDEN_KEYS.has(key) && !key.endsWith('_id'))
    .map(([key, item]) => [key, sanitizeDisplay(item)]));
}

export function parseCallContent(value: unknown): ParsedContent {
  if (typeof value !== 'string') return { kind: 'json', data: value };
  const trimmed = value.trim();
  const fenced = trimmed.match(/^```(?:json|tool_call)?\s*\n?([\s\S]*?)\n?```$/i);
  const candidate = fenced?.[1]?.trim() ?? trimmed;
  try {
    const data = JSON.parse(candidate) as unknown;
    const record = asRecord(data);
    return { kind: fenced && ('tool' in record || 'arguments' in record) ? 'tool_call' : 'json', data };
  } catch {
    return { kind: 'text', text: value };
  }
}

function hasContent(value: unknown): boolean {
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return Object.keys(asRecord(value)).length > 0;
}

export function llmResponseContent(payload: Record<string, unknown>): unknown {
  return [payload.parsed_response, payload.response, payload.content].find(hasContent);
}

export function llmResponseStatus(payload: Record<string, unknown>): 'answered' | 'empty' | 'error' {
  if (typeof payload.error_type === 'string' && payload.error_type.trim()) return 'error';
  return hasContent(llmResponseContent(payload)) ? 'answered' : 'empty';
}

export function llmMessages(payload: Record<string, unknown>): Array<{ role: string; content: ParsedContent }> {
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  return messages.map((message) => {
    const record = asRecord(message);
    return { role: String(record.role ?? 'message'), content: parseCallContent(record.content ?? record) };
  });
}

export function toolResult(payload: Record<string, unknown>): { success?: boolean; message?: string; data: unknown; details: DisplayEntry[] } {
  const nested = asRecord(payload.result);
  const success = typeof payload.success === 'boolean' ? payload.success : typeof nested.success === 'boolean' ? nested.success : undefined;
  const message = typeof payload.safe_message === 'string' ? payload.safe_message : typeof nested.safe_message === 'string' ? nested.safe_message : undefined;
  return {
    success,
    message,
    data: nested.data ?? payload.data,
    details: toDisplayEntries({
      ...payload,
      ...nested,
      success: success === true ? 'Успешно' : success === false ? 'Ошибка' : undefined,
      safe_message: message,
    }),
  };
}

export function rawCallEvents(request: RuntimeJournalEvent, response?: RuntimeJournalEvent): unknown[] {
  return [request, ...(response ? [response] : [])].map((event) => ({
    sequence: event.sequence,
    event_type: event.event_type,
    occurred_at: event.occurred_at,
    entity_type: event.entity_type,
    entity_id: event.entity_id,
    parent_entity_type: event.parent_entity_type,
    parent_entity_id: event.parent_entity_id,
    duration_ms: event.duration_ms,
    payload: event.payload,
  }));
}
