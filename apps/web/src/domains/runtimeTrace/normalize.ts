import type { RunTrace, SemanticEvent, TraceCategory, TraceSourceStep, TraceStatus } from './types';

const CATEGORY_MAP: Record<string, TraceCategory> = {
  user_request: 'input',
  budget_policy: 'budget',
  budget_consumed: 'budget',
  budget_limit_exceeded: 'budget',
  llm_call: 'llm',
  llm_request: 'llm',
  llm_response: 'llm',
  routing: 'decision',
  protocol_retry: 'retry',
  planner_action: 'planner',
  planner_step: 'planner',
  operation_call: 'operation',
  tool_call: 'operation',
  operation_result: 'operation',
  tool_result: 'operation',
  policy_decision: 'policy',
  confirmation_required: 'policy',
  final: 'final',
  final_response: 'final',
  error: 'error',
  status: 'system',
  thinking: 'system',
  delta: 'system',
  waiting_input: 'system',
  run_paused: 'system',
  stop: 'system',
  done: 'system',
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
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
  if (rawType === 'user_request') return String(data.content ?? data.request ?? 'User request');
  if (rawType === 'protocol_retry') return String(data.reason ?? 'Protocol retry');
  if (rawType === 'routing') return String(data.agent_slug ?? data.mode ?? 'Routing decision');
  if (rawType === 'operation_call' || rawType === 'tool_call') {
    return String(data.operation_slug ?? data.tool ?? data.operation ?? 'Operation call');
  }
  if (rawType === 'operation_result' || rawType === 'tool_result') {
    const ok = data.success;
    const status = typeof ok === 'boolean' ? (ok ? 'success' : 'failed') : 'result';
    return `${String(data.operation_slug ?? data.tool ?? data.operation ?? 'Operation')} ${status}`;
  }
  if (rawType === 'llm_call' || rawType === 'llm_response') {
    return `response_length=${String(data.response_length ?? data.tokens_out ?? 'n/a')}`;
  }
  if (rawType === 'budget_consumed') {
    return `used=${String(data.consumed ?? data.used ?? data.steps_used ?? 'n/a')}`;
  }
  if (rawType === 'final' || rawType === 'final_response') {
    return String(data.content ?? data.answer ?? 'Final response');
  }
  if (rawType === 'error') return String(data.error ?? data.message ?? 'Error');
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
  return 'system';
}

function titleOf(rawType: string, category: TraceCategory): string {
  const titles: Record<string, string> = {
    user_request: 'Запрос',
    budget_policy: 'Лимиты',
    budget_consumed: 'Расход лимитов',
    llm_call: 'LLM вызов',
    llm_request: 'LLM запрос',
    llm_response: 'LLM ответ',
    routing: 'Маршрутизация',
    protocol_retry: 'Повтор протокола',
    operation_call: 'Вызов операции',
    tool_call: 'Вызов операции',
    operation_result: 'Результат операции',
    tool_result: 'Результат операции',
    planner_action: 'Планировщик',
    planner_step: 'Планировщик',
    policy_decision: 'Решение политики',
    confirmation_required: 'Требуется подтверждение',
    final: 'Финальный ответ',
    final_response: 'Финальный ответ',
    error: 'Ошибка',
  };
  return titles[rawType] ?? `${category}: ${rawType}`;
}

export function normalizeTraceEvent(step: TraceSourceStep): SemanticEvent {
  const rawType = step.raw_type;
  const category = CATEGORY_MAP[rawType] ?? 'system';
  const iteration = pickIteration(step);
  const summary = summarize(rawType, step.data);

  const inputs = rawType === 'operation_call' || rawType === 'tool_call'
    ? { arguments: step.data.arguments ?? step.data.parameters ?? step.data.input ?? step.data.payload }
    : rawType === 'user_request'
      ? { content: step.data.content ?? step.data.request }
      : undefined;

  const outputs = rawType === 'operation_result' || rawType === 'tool_result'
    ? { result: step.data.result ?? step.data.output ?? step.data.data }
    : rawType === 'llm_response' || rawType === 'final_response' || rawType === 'final'
      ? { content: step.data.content ?? step.data.answer ?? step.data.response }
      : undefined;

  const budget = rawType.startsWith('budget_') ? step.data : undefined;

  return {
    id: step.id,
    raw_type: rawType,
    category,
    title: titleOf(rawType, category),
    summary,
    status: statusOf(rawType, step.data),
    phase: phaseOf(category),
    iteration,
    started_at: step.created_at,
    duration_ms: step.duration_ms,
    inputs,
    outputs,
    decision: category === 'decision' || category === 'planner' || category === 'policy' || category === 'retry' ? step.data : undefined,
    budget,
    refs: asRecord(step.data.refs),
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
