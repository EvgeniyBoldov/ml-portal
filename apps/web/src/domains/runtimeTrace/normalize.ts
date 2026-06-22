import type { RunTrace, SemanticEvent, TraceCategory, TraceSourceStep, TraceStatus } from './types';
import { parseBudgetSnapshot } from './budget';

const CATEGORY_MAP: Record<string, TraceCategory> = {
  user_request: 'input',
  budget_snapshot: 'budget',
  llm_call: 'llm',
  llm_request: 'llm',
  llm_response: 'llm',
  llm_turn: 'llm',
  routing: 'decision',
  protocol_retry: 'retry',
  planner_action: 'planner',
  planner_step: 'planner',
  planner_decision: 'planner',
  planner_iteration_start: 'planner',
  planner_iteration_end: 'planner',
  intent: 'planner',
  operation_call: 'operation',
  tool_call: 'operation',
  operation_result: 'operation',
  tool_result: 'operation',
  policy_decision: 'policy',
  confirmation_required: 'policy',
  question_answer: 'system',
  final: 'final',
  final_response: 'final',
  error: 'error',
  // Lifecycle — run
  run_start: 'system',
  run_end: 'system',
  // Lifecycle — orchestrator
  orchestrator_start: 'system',
  orchestrator_end: 'system',
  // Lifecycle — agent
  agent_start: 'system',
  agent_end: 'system',
  // Lifecycle — synthesis
  synthesis_start: 'system',
  synthesis_end: 'system',
  // Other system
  status: 'system',
  delta: 'system',
  waiting_input: 'system',
  final_answer_marker: 'system',
  run_paused: 'system',
  stop: 'system',
  done: 'system',
  partial_mode: 'system',
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function parseJsonRecord(value: unknown): Record<string, unknown> | undefined {
  if (typeof value !== 'string') return undefined;
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return undefined;
    return parsed as Record<string, unknown>;
  } catch {
    return undefined;
  }
}

function inferLlmRole(data: Record<string, unknown>): { role: string; label: string } {
  const purpose = String(data.purpose ?? '').trim().toLowerCase();
  const parsed = asRecord(data.parsed_response);
  const contentText = typeof data.content === 'string'
    ? data.content
    : typeof data.response === 'string'
      ? data.response
      : typeof data.text === 'string'
        ? data.text
        : undefined;
  const parsedFromContent = parseJsonRecord(contentText);
  if (purpose === 'planning_decision' && (Array.isArray(parsed.hypotheses) || Array.isArray(parsedFromContent?.hypotheses))) {
    return { role: 'reasoning', label: 'Рассуждение' };
  }
  if (purpose === 'planning_decision') {
    return { role: 'planner_decision', label: 'Следующий шаг' };
  }
  if (purpose === 'tool_decision_or_answer' && String(contentText ?? '').trim().startsWith('```operation_call')) {
    return { role: 'tool_protocol', label: 'Протокол инструмента' };
  }
  if (purpose === 'tool_decision_or_answer') {
    return { role: 'agent_answer', label: 'Ответ агента' };
  }
  if (purpose === 'fact_extractor' || purpose === 'summary_compactor') {
    return { role: 'memory', label: purpose === 'fact_extractor' ? 'Извлечение фактов' : 'Сводка памяти' };
  }
  if (purpose === 'final_answer') {
    return { role: 'final_answer', label: 'Финальный ответ' };
  }
  return { role: 'generic', label: 'LLM вызов' };
}

function inferErrorLabel(data: Record<string, unknown>): string {
  const code = String(data.error_code ?? '').trim().toLowerCase();
  const phase = String(asRecord(data._envelope).phase ?? '').trim().toLowerCase();
  if (code === 'agent_required_operation_call_missing') return 'Нарушение контракта агента';
  if (code.startsWith('tool_') || code.includes('operation')) return 'Ошибка инструмента';
  if (code.startsWith('llm_')) return 'Ошибка LLM';
  if (phase === 'agent' || phase === 'planner' || code.startsWith('agent_') || code.startsWith('runtime_')) return 'Ошибка рантайма';
  return 'Ошибка';
}

function pickIteration(step: TraceSourceStep): number {
  const data = step.data;
  const direct = data.iteration ?? data.step;
  if (typeof direct === 'number' && Number.isFinite(direct) && direct >= 0) {
    return Math.floor(direct);
  }
  const env = asRecord(data._envelope);
  const sequence = env.sequence;
  if (typeof sequence === 'number' && Number.isFinite(sequence) && sequence >= 0) {
    return Math.floor(sequence);
  }
  if (typeof step.step_number === 'number' && Number.isFinite(step.step_number)) {
    return step.step_number;
  }
  return 0;
}

function summarize(rawType: string, data: Record<string, unknown>): string {
  const llmPurpose = String(data.purpose ?? data.step_kind ?? data.stepKind ?? '').trim();
  const llmModel = String(data.model ?? data.provider_model ?? '').trim();
  if (rawType === 'user_request') return String(data.content ?? data.request ?? 'User request');
  if (rawType === 'protocol_retry') return String(data.reason ?? 'Protocol retry');
  if (rawType === 'confirmation_required') {
    return String(data.summary ?? data.message ?? 'Confirmation required');
  }
  if (rawType === 'waiting_input') {
    return String(data.question ?? data.message ?? 'Waiting for input');
  }
  if (rawType === 'question_answer') {
    const question = String(data.question ?? '').trim();
    const answer = String(data.user_answer ?? data.answer ?? '').trim();
    if (question && answer) return `${question} → ${answer}`;
    return question || answer || 'Question answered';
  }
  if (rawType === 'routing') return String(data.agent_slug ?? data.mode ?? 'Routing decision');
  if (rawType === 'planner_action' || rawType === 'planner_step' || rawType === 'planner_decision') {
    const kind = String(data.kind ?? data.action_type ?? data.action ?? 'planner_decision');
    if (kind === 'thinking') {
      return String(data.selected_action_summary ?? data.selection_rationale ?? 'Thinking');
    }
    const rationale = String(data.rationale ?? '').trim();
    return rationale ? `${kind}: ${rationale}` : kind;
  }
  if (rawType === 'intent') {
    return String(data.description ?? 'Intent');
  }
  if (rawType === 'operation_call' || rawType === 'tool_call') {
    return String(data.operation_slug ?? data.tool ?? data.operation ?? 'Operation call');
  }
  if (rawType === 'operation_result' || rawType === 'tool_result') {
    const ok = data.success;
    const status = typeof ok === 'boolean' ? (ok ? 'success' : 'failed') : 'result';
    const base = `${String(data.operation_slug ?? data.tool ?? data.operation ?? 'Operation')} ${status}`;
    if (ok === false) {
      const details = String(data.safe_message ?? data.error ?? data.message ?? data.error_code ?? '').trim();
      return details ? `${base}: ${details}` : base;
    }
    return base;
  }
  if (rawType === 'llm_call' || rawType === 'llm_response' || rawType === 'llm_turn') {
    const roleMeta = inferLlmRole(data);
    const parsed = asRecord(data.parsed_response);
    const thinkingSummary = String(parsed.selected_action_summary ?? data.selected_action_summary ?? '').trim();
    const error = String(data.error ?? data.error_code ?? '').trim();
    if (thinkingSummary) return thinkingSummary;
    if (roleMeta.role === 'reasoning') return roleMeta.label;
    if (roleMeta.role === 'planner_decision') return roleMeta.label;
    if (roleMeta.role === 'tool_protocol') return roleMeta.label;
    if (roleMeta.role === 'memory') return roleMeta.label;
    if (roleMeta.role === 'final_answer') return roleMeta.label;
    if (llmPurpose) return llmModel ? `${llmPurpose} · ${llmModel}` : llmPurpose;
    if (error) return error;
    const tokensOut = data.tokens_out ?? data.response_length;
    return tokensOut !== undefined ? `tokens_out=${String(tokensOut)}` : (llmModel ? `model=${llmModel}` : 'LLM');
  }
  if (rawType === 'llm_request') {
    const model = String(data.model ?? data.provider_model ?? 'unknown');
    return `model=${model}`;
  }
  if (rawType === 'budget_snapshot') {
    const entityType = String(data.entity_type ?? data.owner_scope ?? 'unknown');
    return `${entityType}: snapshot`;
  }
  if (rawType === 'final' || rawType === 'final_response') {
    return String(data.content ?? data.answer ?? 'Final response');
  }
  if (rawType === 'error') return String(data.error ?? data.message ?? inferErrorLabel(data));
  // Lifecycle events
  if (rawType === 'planner_iteration_start') {
    return `Iteration ${String(data.iteration ?? 1)}`;
  }
  if (rawType === 'planner_iteration_end') {
    return `Iteration ${String(data.iteration ?? 1)}: ${String(data.status ?? 'done')}`;
  }
  if (rawType === 'agent_start') {
    return `Agent: ${String(data.agent_slug ?? 'unknown')}`;
  }
  if (rawType === 'agent_end') {
    return `Agent ${String(data.agent_slug ?? 'unknown')}: ${String(data.status ?? 'done')}`;
  }
  if (rawType === 'orchestrator_start') return String(data.role ?? 'orchestrator');
  if (rawType === 'orchestrator_end') return `${String(data.role ?? 'orchestrator')}: ${String(data.status ?? 'done')}`;
  if (rawType === 'synthesis_start') return 'synthesis';
  if (rawType === 'synthesis_end') return `synthesis: ${String(data.status ?? 'done')}`;
  if (rawType === 'run_start') return String(data.entity_id ?? 'run');
  if (rawType === 'run_end') return `run: ${String(data.status ?? 'done')}`;
  if (rawType === 'final_answer_marker') return `final: ${String(data.producer ?? 'unknown')}`;
  return Object.keys(data).length > 0 ? JSON.stringify(data).slice(0, 180) : rawType;
}

function statusOf(rawType: string, data: Record<string, unknown>): TraceStatus {
  if (rawType === 'error') return 'error';
  if (rawType === 'protocol_retry' || rawType === 'confirmation_required') return 'warn';
  if ((rawType === 'operation_result' || rawType === 'tool_result') && data.success === false) return 'error';
  if (rawType === 'final' || rawType === 'final_response') return 'ok';
  return 'info';
}

function phaseOf(category: TraceCategory): string {
  if (category === 'input') return 'input';
  if (category === 'budget') return 'budget';
  if (category === 'llm') return 'llm';
  if (category === 'decision' || category === 'planner' || category === 'retry' || category === 'policy') return 'decision';
  if (category === 'operation') return 'operation';
  if (category === 'final' || category === 'error') return 'final';
  if (category === 'unknown') return 'unknown';
  return 'system';
}

function phaseFromEnvelopeOrCategory(data: Record<string, unknown>, category: TraceCategory): string {
  const env = asRecord(data._envelope);
  const envelopePhase = env.phase;
  if (typeof envelopePhase === 'string' && envelopePhase.trim()) {
    return envelopePhase.trim().toLowerCase();
  }
  return phaseOf(category);
}

function titleOf(rawType: string, category: TraceCategory, data?: Record<string, unknown>): string {
  const titles: Record<string, string> = {
    user_request: 'Запрос',
    budget_snapshot: 'Снимок бюджета',
    llm_call: 'LLM вызов',
    llm_request: 'LLM запрос',
    llm_response: 'LLM ответ',
    llm_turn: 'LLM турн',
    routing: 'Маршрутизация',
    protocol_retry: 'Повтор протокола',
    operation_call: 'Вызов операции',
    tool_call: 'Вызов операции',
    operation_result: 'Результат операции',
    tool_result: 'Результат операции',
    planner_action: 'Планировщик',
    planner_step: 'Планировщик',
    planner_decision: 'Решение планировщика',
    planner_iteration_start: 'Итерация плана: старт',
    planner_iteration_end: 'Итерация плана: конец',
    intent: 'Интент',
    policy_decision: 'Решение политики',
    confirmation_required: 'Требуется подтверждение',
    waiting_input: 'Запрос уточнения',
    question_answer: 'Вопрос-ответ',
    final: 'Финальный ответ',
    final_response: 'Финальный ответ',
    error: 'Ошибка',
    run_start: 'Запуск run',
    run_end: 'Завершение run',
    orchestrator_start: 'Оркестратор: старт',
    orchestrator_end: 'Оркестратор: конец',
    agent_start: 'Агент: старт',
    agent_end: 'Агент: конец',
    synthesis_start: 'Синтез: старт',
    synthesis_end: 'Синтез: конец',
    final_answer_marker: 'Маркер финального ответа',
    run_paused: 'Пауза выполнения',
    stop: 'Остановлено',
  };
  if (rawType === 'llm_turn' && data) return inferLlmRole(data).label;
  if (rawType === 'error' && data) return inferErrorLabel(data);
  return titles[rawType] ?? `${category}: ${rawType}`;
}

// System-level events that should NOT be marked as 'unknown' even if not in CATEGORY_MAP
const SYSTEM_EVENT_PATTERNS = ['status', 'delta', 'waiting', 'stop', 'done', 'run_', 'intent'];

function isSystemEvent(rawType: string): boolean {
  return SYSTEM_EVENT_PATTERNS.some(pattern => rawType.toLowerCase().includes(pattern));
}

function extractBudgetPayload(rawType: string, data: Record<string, unknown>): Record<string, unknown> | undefined {
  if (rawType !== 'budget_snapshot') return undefined;
  const parsed = parseBudgetSnapshot(data);
  return parsed ? { ...data, _parsed: parsed } : data;
}

export function normalizeTraceEvent(step: TraceSourceStep): SemanticEvent {
  const rawType = step.raw_type;
  const category = CATEGORY_MAP[rawType] ?? (isSystemEvent(rawType) ? 'system' : 'unknown');
  const iteration = pickIteration(step);
  const summary = summarize(rawType, step.data);

  const inputs = rawType === 'operation_call' || rawType === 'tool_call'
    ? { arguments: step.data.arguments ?? step.data.parameters ?? step.data.input ?? step.data.payload }
    : rawType === 'user_request'
      ? { content: step.data.content ?? step.data.request }
      : undefined;

  const outputs = rawType === 'operation_result' || rawType === 'tool_result'
    ? { result: step.data.result ?? step.data.output ?? step.data.data }
    : rawType === 'llm_response' || rawType === 'llm_turn'
      ? { content: step.data.response ?? step.data.raw_response ?? step.data.content, parsed_response: step.data.parsed_response }
    : rawType === 'question_answer'
      ? { answer: step.data.user_answer ?? step.data.answer }
    : rawType === 'final_response' || rawType === 'final'
      ? { content: step.data.content ?? step.data.answer ?? step.data.response }
      : undefined;

  const llmRequestInputs = rawType === 'llm_request' || rawType === 'llm_turn'
    ? {
        messages: step.data.messages ?? step.data.messages_sent,
        payload: step.data.payload ?? step.data.request_payload,
        system_prompt: step.data.system_prompt ?? step.data.compiled_prompt ?? step.data.prompt,
        model: step.data.model ?? step.data.provider_model,
      }
    : rawType === 'waiting_input' || rawType === 'confirmation_required'
      ? {
          question: step.data.question ?? step.data.message,
          action: step.data.action,
          context: step.data.context,
        }
    : rawType === 'question_answer'
      ? { question: step.data.question }
    : undefined;

  const budget = extractBudgetPayload(rawType, step.data);

  const lifecycleRefs: Record<string, unknown> = {};
  if (step.data.entity_id) lifecycleRefs.entity_id = step.data.entity_id;
  if (step.data.entity_type) lifecycleRefs.entity_type = step.data.entity_type;
  if (step.data.parent_entity_id) lifecycleRefs.parent_entity_id = step.data.parent_entity_id;
  if (step.data.parent_entity_type) lifecycleRefs.parent_entity_type = step.data.parent_entity_type;
  if (step.data.agent_slug) lifecycleRefs.agent_slug = step.data.agent_slug;
  if (step.data.agent_run_id) lifecycleRefs.agent_run_id = step.data.agent_run_id;
  if (step.data.llm_call_id) lifecycleRefs.llm_call_id = step.data.llm_call_id;

  const refs = Object.keys(lifecycleRefs).length > 0
    ? { ...asRecord(step.data.refs), ...lifecycleRefs }
    : asRecord(step.data.refs);

  return {
    id: step.id,
    raw_type: rawType,
    category,
    title: titleOf(rawType, category, step.data),
    summary,
    status: statusOf(rawType, step.data),
    phase: phaseFromEnvelopeOrCategory(step.data, category),
    iteration,
    started_at: step.created_at,
    duration_ms: step.duration_ms,
    inputs: llmRequestInputs ?? inputs,
    outputs,
    decision: category === 'decision' || category === 'planner' || category === 'policy' || category === 'retry' ? step.data : undefined,
    budget,
    refs,
    raw: {
      id: step.id,
      raw_type: rawType,
      raw: step.data,
    },
  };
}

export function buildRunTrace(steps: TraceSourceStep[]): RunTrace {
  const events = steps.map(normalizeTraceEvent);
  const buckets = new Map<number, SemanticEvent[]>();

  for (const event of events) {
    const key = event.iteration;
    const list = buckets.get(key) ?? [];
    list.push(event);
    buckets.set(key, list);
  }

  const iterations = Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([index, list]) => ({ index, events: list }));

  return {
    iterations,
    total_events: events.length,
  };
}
