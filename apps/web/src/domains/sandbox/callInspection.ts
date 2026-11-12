export type DisplayEntry = { label: string; value: unknown };
export type ParsedContent = { text?: string; data?: unknown; kind: 'text' | 'json' | 'tool_call' };
export type ToolNameMap = ReadonlyMap<string, string>;
export type LlmOutcomeKind = 'tools' | 'answer' | 'clarify' | 'plan' | 'empty' | 'error';
export type LlmOutcome = { kind: LlmOutcomeKind; label: string; count?: number };

const HIDDEN_KEYS = new Set([
  '_envelope', 'entity_id', 'entity_type', 'row_id', 'parent_entity_id', 'parent_entity_type',
  'actor_entity_id', 'actor_type', 'agent_execution_id', 'call_id', 'llm_call_id',
  'planner_iteration_id', 'planner_run_id', 'run_id', 'chat_id', 'storage_uri',
  'debug', 'traceback', 'messages', 'parsed_response', 'response',
  'template_schema', 'runtime_schema', 'schema', 'locator', 'artifact_id',
  '_progress', 'agent_slug', 'structured_input', 'step_kind', 'native_tool_calling',
  'response_length', 'reused_from_call_id', 'user_message', 'operator_message',
  'mcp_failure', 'result_envelope',
  'result_id', 'source_result_id', 'source_result_ids', 'sql_ref', 'query_sql',
  'collection_id', 'provider_id', 'data_instance_id', 'credential_id',
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
  status_code: 'HTTP-статус', provider_code: 'Код провайдера', retry_after_ms: 'Повтор через',
  error_type: 'Тип ошибки', timeout_s: 'Тайм-аут', format: 'Формат',
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

export function formatFieldLabel(key: string): string {
  const known = LABELS[key];
  if (known) return known;
  const text = key
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .replace(/[_.-]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
  return text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}` : key;
}

export function toDisplayEntries(value: unknown): DisplayEntry[] {
  return Object.entries(asRecord(value))
    .filter(([key, raw]) => !HIDDEN_KEYS.has(key) && raw !== null && raw !== undefined && raw !== '')
    .map(([key, raw]) => ({
      label: formatFieldLabel(key),
      value: key === 'purpose' ? purposeLabel(raw) : key === 'tool' || key === 'operation_slug' ? callDisplayName(String(raw)) : sanitizeDisplay(raw),
    }));
}

export function sanitizeDisplay(value: unknown): unknown {
  if (typeof value === 'string' && /^(s3|https?):\/\//i.test(value)) return '[скрытый адрес источника]';
  if (Array.isArray(value)) return value.map(sanitizeDisplay);
  const source = asRecord(value);
  if (Object.keys(source).length === 0) return value;
  return Object.fromEntries(Object.entries(source)
    .filter(([key, item]) => !HIDDEN_KEYS.has(key) && !(key === 'source' && typeof item === 'string' && /^(s3|https?):\/\//i.test(item)))
    .map(([key, item]) => [key, sanitizeDisplay(item)]));
}

export function parseCallContent(value: unknown): ParsedContent {
  if (typeof value !== 'string') return { kind: 'json', data: value };
  const trimmed = value.trim();
  const fenced = trimmed.match(/^```(?:json|tool_call|tool_result)?\s*\n?([\s\S]*?)\n?```$/i);
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
  if ((typeof payload.error_type === 'string' && payload.error_type.trim())
    || (typeof payload.error_code === 'string' && payload.error_code.trim() && !hasContent(llmResponseContent(payload)))) return 'error';
  return hasContent(llmResponseContent(payload)) ? 'answered' : 'empty';
}

export function llmOutcome(payload: Record<string, unknown>, toolCallCount = 0): LlmOutcome {
  if (typeof payload.error_type === 'string' && payload.error_type.trim()) return { kind: 'error', label: 'Ошибка' };
  if (toolCallCount > 0) return { kind: 'tools', label: 'Вызов инструментов', count: toolCallCount };

  const resultKind = typeof payload.result_kind === 'string' ? payload.result_kind : '';
  const resultLabels: Record<string, LlmOutcome> = {
    plan: { kind: 'plan', label: 'План' },
    tool_calls: { kind: 'tools', label: 'Вызов инструментов' },
    answer: { kind: 'answer', label: 'Ответ' },
    clarification: { kind: 'clarify', label: 'Уточнение' },
    empty: { kind: 'empty', label: 'Пусто' },
    error: { kind: 'error', label: 'Ошибка' },
  };
  if (resultLabels[resultKind]) return resultLabels[resultKind];

  const content = llmResponseContent(payload);
  if (!hasContent(content)) return { kind: 'empty', label: 'Пусто' };

  const parsed = parseCallContent(content);
  const data = asRecord(parsed.data);
  if (parsed.kind === 'tool_call' || (data.tool !== undefined && data.arguments !== undefined)) return { kind: 'tools', label: 'Вызов инструментов', count: 1 };
  const isPlanningDecision = payload.purpose === 'planning_decision';
  const terminal = String(data.terminal ?? '').trim();
  if (isPlanningDecision && Array.isArray(data.tasks) && (terminal === 'planner' || terminal === 'synthesis')) {
    const tasks = data.tasks.length;
    return { kind: 'plan', label: terminal === 'planner' ? 'Следующая итерация' : 'Итерация', count: tasks || undefined };
  }
  return { kind: 'answer', label: 'Ответ' };
}

export function llmMessages(payload: Record<string, unknown>): Array<{ role: string; content: ParsedContent }> {
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  return messages.map((message) => {
    const record = asRecord(message);
    return { role: String(record.role ?? 'message'), content: parseCallContent(record.content ?? record) };
  });
}

export type ToolFailure = { category?: string; code?: string; userMessage: string; details?: unknown; inconsistentSuccess?: boolean };

export const safeFailureMessage = (category: unknown, code: unknown): string => {
  const categoryKey = typeof category === 'string' ? category.toLowerCase() : '';
  const codeKey = typeof code === 'string' ? code.toLowerCase() : '';
  const mcpCategories: Record<string, string> = {
    input: 'Источник отклонил параметры запроса.',
    auth: 'Сервис отклонил данные авторизации.',
    access: 'У учётной записи нет доступа к запрошенным данным.',
    availability: 'Сервис операции временно недоступен.',
    rate_limit: 'Сервис временно ограничил частоту запросов.',
    unknown: 'Операция не выполнена.',
  };
  if (mcpCategories[categoryKey]) return mcpCategories[categoryKey];
  const runtimeCodes: Record<string, string> = {
    operation_unavailable: 'Операция сейчас недоступна.',
    operation_ambiguous: 'Не удалось однозначно выбрать операцию.',
    operation_invalid_args: 'Не удалось выполнить операцию: проверьте переданные параметры.',
    operation_timeout: 'Операция не завершилась вовремя.',
    operation_execution_failed: 'Не удалось выполнить операцию.',
    operation_confirmation_required: 'Для продолжения требуется подтверждение.',
    agent_wall_time_exceeded: 'Время выполнения задачи исчерпано.',
    agent_required_operation_call_missing: 'Не выполнена обязательная операция.',
    agent_max_tool_calls_exceeded: 'Достигнут предел числа операций.',
    agent_max_retries_exceeded: 'Не удалось выполнить операцию после повторных попыток.',
    agent_non_retryable_operation_failure: 'Операция не выполнена и не может быть повторена автоматически.',
    agent_no_successful_operation_result: 'Операция не вернула подтверждённый результат.',
    agent_runtime_exception: 'Во время выполнения возникла проблема.',
    agent_precheck_failed: 'Не удалось подготовить исполнение задачи.',
    agent_unavailable: 'Исполнитель задачи временно недоступен.',
    agent_no_operations: 'Для задачи не настроены доступные операции.',
    budget_exceeded: 'Лимит выполнения задачи исчерпан.',
    llm_timeout: 'Модель не ответила вовремя.',
    llm_context_window_exceeded: 'Запрос не помещается в доступный контекст модели.',
    llm_input_limit_exceeded: 'Размер запроса превышает допустимый предел модели.',
    llm_output_limit_exceeded: 'Размер ответа превышает допустимый предел модели.',
    turn_preflight_unavailable: 'Не удалось проверить готовность и выбрать маршрут.',
  };
  if (runtimeCodes[codeKey]) return runtimeCodes[codeKey];
  return 'Операция не выполнена.';
};

function recordAt(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function failureFrom(payload: Record<string, unknown>): ToolFailure | undefined {
  const envelope = recordAt(payload.result_envelope);
  const nested = recordAt(payload.result);
  const candidates = [payload.mcp_failure, envelope?.failure, nested?.failure, payload.failure];
  for (const candidate of candidates) {
    const failure = recordAt(candidate);
    if (!failure || failure.version !== 1) continue;
    const category = typeof failure.category === 'string' ? failure.category : undefined;
    const code = typeof failure.code === 'string' ? failure.code : undefined;
    const details = {
      kind: failure.kind,
      category: failure.category,
      code: failure.code,
      message: failure.message,
      stage: failure.stage,
      http_status: failure.http_status,
      rpc_code: failure.rpc_code,
      details: failure.details ?? failure.source_error ?? failure.error,
    };
    return { category, code, userMessage: safeFailureMessage(category, code), details };
  }
  return undefined;
}

export function toolResult(payload: Record<string, unknown>): { success?: boolean; message?: string; data: unknown; details: DisplayEntry[]; failure?: ToolFailure; diagnostic?: unknown; resultId?: string; revision?: number; recoveryReason?: string; delivery?: string; storedDescriptor: boolean; inlineComplete?: boolean; sourceComplete?: boolean; sourceTotal?: number; returnedCount?: number; receivedCount?: number; queryComplete?: boolean; readComplete?: boolean; pageMayHaveMore?: boolean; truncated: boolean } {
  const nested = asRecord(payload.result);
  const envelope = asRecord(payload.result_envelope);
  const failure = failureFrom(payload);
  const explicitOutcomes = [payload.success, envelope.success, nested.success]
    .filter((value): value is boolean => typeof value === 'boolean');
  const statusOutcomes = [payload.status, envelope.status, nested.status].flatMap((status) => {
    if (status === 'succeeded' || status === 'success' || status === 'completed') return [true];
    if (status === 'failed' || status === 'error') return [false];
    return [];
  });
  const explicitSuccess = explicitOutcomes[0];
  const outcomes = [...explicitOutcomes, ...statusOutcomes];
  const conflictingOutcomes = new Set(outcomes).size > 1;
  const inconsistent = conflictingOutcomes || Boolean(failure && outcomes.includes(true));
  const success = inconsistent ? undefined : failure ? false : explicitSuccess ?? statusOutcomes[0];
  if (inconsistent && failure) failure.inconsistentSuccess = true;
  const safeMessage = [payload.user_message, envelope.user_message, nested.user_message]
    .find((value) => typeof value === 'string' && value.trim());
  const legacyCode = payload.error_code ?? nested.error_code;
  const legacyFailure = explicitOutcomes.includes(false) || statusOutcomes.includes(false);
  const legacySafeMessage = payload.safe_message ?? nested.safe_message;
  const knownLegacyMessage = legacyFailure && failure === undefined
    && typeof legacySafeMessage === 'string'
    && legacySafeMessage.trim() === 'q is required'
    ? 'Не задан поисковый запрос.'
    : undefined;
  const legacyDiagnostics = legacyFailure ? {
    category: payload.error_type ?? nested.error_type,
    code: legacyCode,
    safe_message: payload.safe_message ?? nested.safe_message,
    message: payload.message ?? nested.message,
    error: payload.error ?? nested.error,
  } : undefined;
  const message = failure?.userMessage ?? knownLegacyMessage ?? (typeof safeMessage === 'string' ? safeMessage : legacyFailure ? safeFailureMessage(undefined, legacyCode) : undefined);
  const rawData = nested.data ?? envelope.data ?? payload.data;
  const dataRecord = asRecord(rawData);
  const runtimeResult = recordAt(dataRecord?._runtime_result);
  const observation = recordAt(payload.result_observation);
  const observationCoverage = recordAt(observation?.source_coverage);
  const descriptorRecord = runtimeResult ?? dataRecord;
  const dataMeta = asRecord(dataRecord?.meta);
  const isResultPage = Boolean(dataRecord && Array.isArray(dataRecord.value) && dataMeta);
  const delivery = [payload.result_delivery, envelope.result_delivery, nested.result_delivery, observation?.delivery, runtimeResult?.delivery]
    .find((value): value is string => typeof value === 'string');
  const resultId = [payload.result_id, envelope.result_id, nested.result_id, observation?.result_id, dataRecord?.result_id, runtimeResult?.result_id]
    .find((value): value is string => typeof value === 'string');
  const hasInlinePayload = Boolean(dataRecord && (
    Array.isArray(dataRecord.value) || Array.isArray(dataRecord.rows) || Array.isArray(dataRecord.sample)
      || typeof dataRecord.text === 'string' || dataRecord.data !== undefined
  ));
  const strongLegacyDescriptor = Boolean(resultId && descriptorRecord && (
    typeof descriptorRecord.sql_ref === 'string' || typeof descriptorRecord.payload_type === 'string'
  ));
  const storedDescriptor = !hasInlinePayload && (
    (delivery === 'stored' && Boolean(resultId) && Boolean(descriptorRecord && (
      'row_count' in descriptorRecord || 'payload_type' in descriptorRecord || 'observed_schema' in descriptorRecord
    ))) || (delivery === undefined && strongLegacyDescriptor)
  );
  const countValue = [payload.result_row_count, envelope.result_row_count, nested.result_row_count, dataRecord?.row_count, runtimeResult?.row_count, dataMeta?.row_count, dataMeta?.returned_count, isResultPage ? (dataRecord?.value as unknown[]).length : undefined, payload.returned_count, envelope.returned_count, nested.returned_count, payload.row_count, nested.row_count]
    .find((value) => typeof value === 'number' && Number.isFinite(value));
  const sourceTotalValue = [payload.result_source_total, envelope.result_source_total, nested.result_source_total, dataRecord?.source_total, runtimeResult?.source_total, dataMeta?.source_total, isResultPage ? dataMeta?.total : undefined, dataRecord?.total, nested.source_total, nested.total]
    .find((value) => typeof value === 'number' && Number.isFinite(value));
  const receivedValue = [payload.returned_count, envelope.returned_count, nested.returned_count, dataRecord?.returned_count, runtimeResult?.returned_count, dataMeta?.returned_count, isResultPage ? (dataRecord?.value as unknown[]).length : undefined]
    .find((value) => typeof value === 'number' && Number.isFinite(value) && value >= 0);
  return {
    success,
    message,
    data: rawData,
    failure,
    diagnostic: failure?.details ?? legacyDiagnostics,
    resultId,
    revision: typeof observation?.revision === 'number' ? observation.revision : undefined,
    recoveryReason: typeof observation?.recovery_reason === 'string' ? observation.recovery_reason : undefined,
    delivery: delivery ?? (storedDescriptor ? 'stored' : undefined),
    storedDescriptor,
    inlineComplete: [payload.result_inline_complete, envelope.result_inline_complete, nested.result_inline_complete, runtimeResult?.inline_complete].find((value): value is boolean => typeof value === 'boolean'),
    sourceComplete: [payload.result_source_complete, envelope.result_source_complete, nested.result_source_complete, observation?.source_complete, observationCoverage?.complete, runtimeResult?.source_complete, dataRecord?.source_complete, dataMeta?.source_complete, isResultPage ? dataMeta?.complete : undefined].find((value): value is boolean => typeof value === 'boolean'),
    sourceTotal: typeof sourceTotalValue === 'number' ? sourceTotalValue : undefined,
    returnedCount: typeof countValue === 'number' ? countValue : undefined,
    receivedCount: typeof receivedValue === 'number' ? receivedValue : undefined,
    queryComplete: [payload.query_complete, envelope.query_complete, nested.query_complete, observation?.query_complete, runtimeResult?.query_complete, dataRecord?.query_complete, dataMeta?.query_complete].find((value): value is boolean => typeof value === 'boolean'),
    readComplete: typeof observation?.read_complete === 'boolean' ? observation.read_complete : undefined,
    pageMayHaveMore: typeof observation?.page_may_have_more === 'boolean' ? observation.page_may_have_more : undefined,
    truncated: payload.truncated === true || envelope.truncated === true || nested.truncated === true || runtimeResult?.sample_complete === false,
    details: toDisplayEntries({
      ...payload,
      ...nested,
      success: inconsistent ? 'Неизвестно: противоречивый результат' : success === true ? 'Успешно' : success === false ? 'Ошибка' : undefined,
      safe_message: message,
    }),
  };
}
