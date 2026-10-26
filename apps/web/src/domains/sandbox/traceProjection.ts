import type { RuntimeJournalEvent, SandboxTraceState, TraceEntity } from './traceState';
import { callDisplayName, llmOutcome, llmResponseContent, llmResponseStatus, parseCallContent, purposeLabel, sanitizeDisplay, toolResult, type LlmOutcome, type ParsedContent } from './callInspection';
import type { CallErrorDetails, CallPresentationStatus } from './callPresentation';
import { callPresentation } from './callPresentation';
import { projectPlan, projectPlanTask, taskStatusLabel, type PlanTaskViewModel, type PlanViewModel } from './planInspection';

export type TraceCallKind = 'llm' | 'tool' | 'clarify' | 'confirm' | 'error';
export type TraceStageKind = 'iteration' | 'route_policy' | 'turn_preflight' | 'memory_preparation' | 'memory_writeback' | 'synthesis';
export type TraceStepKind = 'planner_decision' | 'task_execution' | 'memory_selection' | 'memory_write' | 'synthesis';
export type TraceExecutorKind = 'planner' | 'preflight' | 'route_policy' | 'agent' | 'memory_selector' | 'fact_extractor' | 'fact_compactor' | 'synthesizer';
export type TraceInspectorTabId = 'info' | 'plan' | 'task' | 'input' | 'route_policy' | 'checkpoint' | 'memory' | 'facts' | 'published' | 'result' | 'prompt' | 'rbac' | 'limits' | 'operations' | 'request' | 'response' | 'error' | 'raw';

export interface TraceInspectorTab {
  id: TraceInspectorTabId;
  label: string;
}

export interface TraceCall {
  entity: TraceEntity;
  /** Canonical journal rows owned by this call entity. */
  events: RuntimeJournalEvent[];
  request: RuntimeJournalEvent;
  response?: RuntimeJournalEvent;
  /** Retry rows explicitly correlated with this LLM call id. */
  retryEvents: RuntimeJournalEvent[];
  /** Tool calls explicitly linked to this LLM call through llm_call_id. */
  linkedToolCalls: RuntimeJournalEvent[];
  kind: TraceCallKind;
  title: string;
  summary?: string;
  toolCallCount?: number;
  extraction?: TraceExtraction;
  /** Typed plan result when this LLM call produced a planning decision. */
  plan?: PlanViewModel;
  /** Logical compatibility id for historical retry rows. */
  logicalLlmCallId?: string;
  /** Legacy attempts, present only when historical rows used separate IDs. */
  attempts?: TraceCall[];
  /** Typed operator-facing fields for semantic inspector tabs. */
  info: TraceCallInfo;
  requestView: TraceCallRequest;
  responseView?: TraceCallResponse;
  errorView?: CallErrorDetails;
}

export interface TraceCallInfo {
  status: CallPresentationStatus;
  durationMs?: number;
  retryCount: number;
  outcome?: LlmOutcome;
  tokensIn?: number;
  tokensOut?: number;
  tokensTotal?: number;
}

export interface TraceCallRequest {
  model?: string;
  purpose?: string;
  temperature?: number;
  maxTokens?: number;
  requestBytes?: number;
  inputTokensEstimate?: number;
  responseSchemaBytes?: number;
  messages: Array<{ role: string; content: ParsedContent }>;
  nativeToolCalls?: unknown[];
  tools?: unknown[];
  responseSchema?: unknown;
  /** Ordered, labelled message transcript for the semantic request tab. */
  messageTranscript?: string;
  toolName?: string;
  description?: string;
  arguments?: unknown;
  question?: string;
  message?: string;
}

export interface TraceToolInvocation {
  name: string;
  arguments?: unknown;
}

export interface TraceToolResult {
  success?: boolean;
  message?: string;
  data: unknown;
  summary: string;
  truncated: boolean;
}

export interface TraceCallResponse {
  resultKind?: string;
  responseLength?: number;
  terminal?: boolean;
  content?: ParsedContent;
  toolCall?: TraceToolInvocation;
  linkedToolCalls: TraceToolInvocation[];
  toolResult?: TraceToolResult;
}

/** Canonical document-extraction subrun owned by a tool call. */
export interface TraceExtraction {
  entity: TraceEntity;
  events: RuntimeJournalEvent[];
  start?: RuntimeJournalEvent;
  end?: RuntimeJournalEvent;
  result: TraceExtractionResult;
}

export interface TraceExtractionResult {
  status: 'running' | 'completed' | 'failed';
  fileName?: string;
  parser?: string;
  contentType?: string;
  contentKind?: string;
  format?: string;
  profile?: string;
  representation?: string;
  truncated?: boolean;
  warnings: string[];
  outputChars?: number;
  durationMs?: number;
  message?: string;
}

export interface TraceLimitRow {
  key: string;
  label: string;
  used?: number;
  limit?: number;
  remaining?: number;
  status: 'neutral' | 'ok' | 'warning' | 'exceeded';
}

export interface TraceLimitsView {
  rows: TraceLimitRow[];
}

export type TraceExecutorStatisticKey = 'llm_calls' | 'tool_calls' | 'tokens_in' | 'tokens_out' | 'tokens_total' | 'llm_retries' | 'llm_errors' | 'tool_errors';

export interface TraceExecutorStatistic {
  key: TraceExecutorStatisticKey;
  label: string;
  value: number;
  limit?: TraceLimitRow;
}

export interface TraceExecutorInfoView {
  status: TraceResultStatus;
  statusLabel: string;
  durationMs?: number;
  statistics: TraceExecutorStatistic[];
}

export interface TraceAccessRow {
  kind: 'Агент' | 'Коллекция';
  name: string;
  allowed: boolean;
  reason: string;
}

export interface TraceAccessView {
  rows: TraceAccessRow[];
  defaultCollectionAllow?: boolean;
}

export interface TraceExecutorRun {
  entity: TraceEntity;
  /** Stable presentation key; differs from the stage key for synthesizer. */
  inspectorKey: string;
  start: RuntimeJournalEvent;
  task: string;
  input?: unknown;
  executorType: string;
  executorName: string;
  executorSlug: string;
  kind: TraceExecutorKind;
  calls: TraceCall[];
  /** Curated terminal result of this executor, prepared from canonical relations. */
  result: TraceExecutorResult;
  info: TraceExecutorInfoView;
  metrics: TraceMetrics;
  memoryResult?: TraceMemoryComponentResult;
  preflight?: TracePreflight;
  /** Normalized turn_preflight routing decision and its input envelope. */
  route?: TraceRoute;
  routePolicy?: TraceRoutePolicy;
  prompt?: TracePrompt;
  access?: TraceAccessView;
  limits?: TraceLimitsView;
  toolOverrides?: TraceToolOverrideSnapshot;
  /** Declared and effective continuation decision for a planner checkpoint. */
  checkpoint?: TraceCheckpointDecision;
  /** Runtime task presentation bound by the trace projector. */
  taskPresentation?: PlanTaskViewModel;
  /** Selected context produced by the memory-preparation executor. */
  memoryContext?: TraceMemoryContext;
}

export interface TraceCheckpointDecision {
  declaredNext?: string;
  effectiveNext?: string;
  reason?: string;
  iterationId?: string;
  decided: boolean;
}

export interface TraceToolOverrideSnapshot {
  configuredPublication: Record<string, boolean>;
  configuredSemantics: Record<string, unknown>;
  effectiveOperations: Array<{
    toolId: string;
    publicationConfigured?: boolean;
    publishedEffective?: boolean;
    configuredSemantics?: unknown;
    effectiveSemantics?: unknown;
  }>;
  suppressedPublication: Array<{ toolId: string; reason?: string }>;
}

export type TraceResultStatus = 'running' | 'completed' | 'failed' | 'unfulfillable' | 'aborted' | 'paused' | 'waiting' | 'unknown';

export interface TraceExecutorResult {
  name: string;
  status: TraceResultStatus;
  statusLabel: string;
  output?: unknown;
  message?: string;
  completionKind?: string;
  sufficientForPhase?: boolean;
  missingInputs?: unknown;
  needs?: unknown;
  artifacts?: unknown;
  sources?: unknown;
  operations: { total: number; succeeded: number; failed: number };
}

export interface TracePrompt {
  text?: string;
  hash?: string;
}

export interface TracePreflight {
  status: string;
  mode?: string;
  durationMs?: number;
  missing: {
    tools: string[];
    collections: string[];
    credentials: string[];
  };
  operationsCount?: number;
  dataInstancesCount?: number;
  access?: TraceAccessView;
}

export interface TraceRoute {
  /** Planner proposal and runtime-selected route are separate journal facts. */
  proposed?: string;
  effective?: string;
  reason?: 'model_selected' | 'runtime_reroute' | 'policy_route';
  detail?: string;
  policyRecommendationId?: string;
  policyDisposition?: 'accepted' | 'modified' | 'rejected' | 'not_applicable';
  policyReasonCode?: string;
  goal?: string;
  direction?: string;
  expectedResult?: string;
  entityHints: string[];
  projectHints: string[];
  constraints: string[];
  input?: unknown;
}

export interface TraceRoutePolicy {
  /** Legacy effective route, present only in historical direct-routing events. */
  route?: string;
  /** New recommendation status; this is not the selected root route. */
  status?: 'matched' | 'unmatched';
  recommendationId?: string;
  routeHint?: string;
  matched?: boolean;
  ruleId?: string;
  reasonCode?: string;
  summary?: string;
  detail?: string;
  signals: string[];
  sourceAgent?: string;
  userRequest?: string;
}

export interface TraceMemoryFact {
  scope: string;
  kind: string;
  subject: string;
  value: string;
  confidence?: number;
  changeType: string;
  statusBefore?: string;
  statusAfter?: string;
  supportBefore?: number;
  supportAfter?: number;
  supportDelta?: number;
  compactionAction?: string;
  decisionReason?: string;
}

export interface TraceMemoryComponentResult {
  componentName: 'fact_extractor' | 'fact_compactor';
  status: string;
  insertedCount: number;
  updatedCount: number;
  skippedCount: number;
  facts: TraceMemoryFact[];
  decisions: TraceMemoryDecision[];
  errorCode?: string;
  errorMessage?: string;
  decisionCounts: Record<string, number>;
  durationMs?: number;
}

export interface TraceMemoryDecision {
  phase: string;
  outcome: string;
  reasonCode: string;
  candidateIds: string[];
  fact?: TraceMemoryFact;
  action?: string;
  evidenceCount?: number;
}

export interface TraceMemoryContext {
  owner?: { kind: string; id: string };
  scopeGroups?: { scope: string; status: string; count: number; error?: string }[];
  fallback: boolean;
  selectedFacts: number;
  selectedProjects: number;
  context: TraceMemoryContextItem[];
  ambiguities: string[];
  selectedGlossary: number;
  selectedMemoryItems: number;
  sourceCheckReasons: string[];
  scopeCandidates?: unknown[];
  scopeAmbiguities?: unknown[];
  truncated?: boolean;
  searchScope?: Record<string, unknown>;
}

export type TraceMemoryContextItem =
  | { type: 'fact'; scope: string; subject: string; value: string }
  | { type: 'project'; projectId?: string; key: string; name: string; matchedAliases: string[] }
  | { type: 'glossary'; scope: string; term: string; description: string; aliases: string[] }
  | { type: 'knowledge'; scope: string; kind: string; subject: string; value: string; confidence?: number; sourceReferences: unknown[]; raw?: Record<string, unknown> };

export interface TraceStage {
  entity: TraceEntity;
  start: RuntimeJournalEvent;
  number: number;
  iterationNumber: number;
  stepNumber: number;
  iterationType: string;
  kind: TraceStageKind;
  label: string;
  task: string;
  /** Planner-owned plan for this revision only. */
  plan?: PlanViewModel;
  /** All canonical steps in this planner iteration, in execution order. */
  steps: TraceStep[];
  executorRuns: TraceExecutorRun[];
  metrics: TraceMetrics;
  failure?: TraceStageFailure;
  routePolicy?: TraceRoutePolicy;
}

export interface TraceStageFailure {
  label: string;
  code?: string;
  message?: string;
}

export interface TraceStep {
  key: string;
  /** Real step entity; synthetic system steps use their owning stage entity. */
  entity: TraceEntity;
  stage: TraceStage;
  number: number;
  kind: TraceStepKind;
  taskId?: string;
  title: string;
  objective?: string;
  inputs?: unknown;
  result?: unknown;
  /** Runtime/planner task presentation prepared by the trace projection. */
  taskPresentation: PlanTaskViewModel;
  executorRuns: TraceExecutorRun[];
  /** Explicitly linked runtime attempts for this logical planner task. */
  attempts?: TraceTaskAttempt[];
  metrics: TraceMetrics;
}

export interface TraceTaskAttempt {
  id: string;
  steps: Array<{ entity: TraceEntity; executorRuns: TraceExecutorRun[] }>;
}

export type TraceInspectionTarget =
  | { kind: 'stage'; key: string; stage: TraceStage; tabs: TraceInspectorTab[] }
  | { kind: 'step'; key: string; step: TraceStep; tabs: TraceInspectorTab[] }
  | { kind: 'executor'; key: string; executor: TraceExecutorRun; stage: TraceStage; tabs: TraceInspectorTab[] }
  | { kind: 'call'; key: string; call: TraceCall; executor: TraceExecutorRun; stage: TraceStage; tabs: TraceInspectorTab[] }
  | { kind: 'error'; key: string; call: TraceCall; executor: TraceExecutorRun; stage: TraceStage; tabs: TraceInspectorTab[] };

export interface TraceMetrics {
  elapsedMs?: number;
  tokens?: number;
  retries?: number;
  calls?: number;
  successfulCalls?: number;
  failedCalls?: number;
}

export interface TraceAttachment {
  artifactId: string;
  fileName: string;
  downloadUrl?: string;
  contentType?: string;
  sizeBytes?: number;
}

export interface TraceRunView {
  runId: string | null;
  status: string;
  finalContent: string;
  attachments: TraceAttachment[];
  sources?: unknown;
  error?: string;
  pause?: { kind: 'input' | 'confirmation'; question?: string; message?: string };
  limits?: TraceLimitsView;
}

const asString = (value: unknown): string => typeof value === 'string' ? value.trim() : '';
const asNumber = (value: unknown): number | undefined => typeof value === 'number' && Number.isFinite(value) ? value : undefined;
const asRecord = (value: unknown): Record<string, unknown> | undefined => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
);
const limitLabels: Record<string, string> = {
  agent_steps: 'Шаги агента', iterations: 'Итерации',
  task_attempts: 'Попытки задач', agent_runs: 'Запуски агентов', llm_calls: 'Вызовы LLM',
  tool_calls: 'Вызовы инструментов', tokens_in: 'Входные токены', tokens_out: 'Выходные токены',
  tokens_total: 'Всего токенов', retries: 'Повторы', wall_time_ms: 'Время выполнения',
  retries_llm_transport: 'Повторы LLM', retries_invalid_tool: 'Повторы проверки инструмента',
};
const limitLabel = (key: string): string => limitLabels[key] ?? key.replace(/_/g, ' ');
const recordNumber = (value: unknown, key: string): number | undefined => asNumber(asRecord(value)?.[key]);

function limitsFor(snapshot: unknown): TraceLimitsView | undefined {
  if (snapshot === undefined || snapshot === null) return undefined;
  const value = asRecord(snapshot) ?? {};
  const nested = asRecord(value.snapshot) ?? {};
  const own = asRecord(value.own) ?? {};
  const limits = asRecord(value.limits ?? value.runtime_limits) ?? {};
  const keys = new Set([...Object.keys(nested), ...Object.keys(own), ...Object.keys(limits)]);
  const rows = [...keys].flatMap((key): TraceLimitRow[] => {
    const metric = asRecord(nested[key]) ?? {};
    if (key === 'retries' && (metric.llm_transport_used !== undefined || metric.invalid_tool_used !== undefined)) {
      return ([
        ['retries_llm_transport', metric.llm_transport_used, metric.limit_per_category, metric.remaining_llm_transport],
        ['retries_invalid_tool', metric.invalid_tool_used, metric.limit_per_category, metric.remaining_invalid_tool],
      ] as const).map(([retryKey, rawUsed, rawLimit, rawRemaining]) => {
        const used = asNumber(rawUsed);
        const limit = asNumber(rawLimit);
        const remaining = asNumber(rawRemaining);
        const status: TraceLimitRow['status'] = limit === undefined ? 'neutral'
          : (used ?? 0) > limit || remaining === 0 ? 'exceeded'
            : (used ?? 0) / limit >= 0.8 ? 'warning' : 'ok';
        return { key: retryKey, label: limitLabel(retryKey), used, limit, remaining, status };
      }).filter((row) => row.used !== undefined || row.limit !== undefined);
    }
    const used = recordNumber(metric, 'used') ?? asNumber(own[key]);
    const limit = recordNumber(metric, 'limit') ?? asNumber(limits[key]);
    const remaining = recordNumber(metric, 'remaining') ?? (limit !== undefined && used !== undefined ? Math.max(0, limit - used) : undefined);
    const status: TraceLimitRow['status'] = limit === undefined
      ? 'neutral'
      : (used ?? 0) > limit || remaining === 0
        ? 'exceeded'
        : (used ?? 0) / limit >= 0.8 ? 'warning' : 'ok';
    return [{ key, label: limitLabel(key), used, limit, remaining, status }];
  }).filter((row) => row.used !== undefined || row.limit !== undefined)
    .sort((left, right) => left.label.localeCompare(right.label, 'ru'));
  return rows.length ? { rows } : undefined;
}

const executorLimitOrder = ['wall_time_ms', 'llm_calls', 'tool_calls', 'tokens_total', 'task_attempts', 'retries_llm_transport', 'retries_invalid_tool', 'retries'];

function executorLimitsFor(snapshot: unknown): TraceLimitsView | undefined {
  const rows = (limitsFor(snapshot)?.rows ?? []).map((row) => row.key === 'agent_steps'
    ? { ...row, key: 'llm_calls', label: limitLabel('llm_calls') }
    : row);
  const filtered = rows
    .filter((row) => row.limit !== undefined && row.key !== 'tokens_in' && row.key !== 'tokens_out')
    .sort((left, right) => {
      const leftOrder = executorLimitOrder.indexOf(left.key);
      const rightOrder = executorLimitOrder.indexOf(right.key);
      return (leftOrder < 0 ? executorLimitOrder.length : leftOrder) - (rightOrder < 0 ? executorLimitOrder.length : rightOrder)
        || left.label.localeCompare(right.label, 'ru');
    });
  return filtered.length ? { rows: filtered } : undefined;
}

function accessFor(snapshot: unknown): TraceAccessView | undefined {
  if (snapshot === undefined || snapshot === null) return undefined;
  const value = asRecord(snapshot) ?? {};
  const rbac = asRecord(value.rbac ?? value) ?? {};
  const collectionFilter = asRecord(rbac.collection_filter) ?? {};
  const rows: TraceAccessRow[] = [];
  const add = (kind: TraceAccessRow['kind'], values: unknown, allowed: boolean, reason: string) => {
    if (!Array.isArray(values)) return;
    for (const item of values) if (typeof item === 'string' && item) rows.push({ kind, name: item, allowed, reason });
  };
  const agentAccess = asRecord(rbac.agent_access);
  if (agentAccess && typeof agentAccess.allowed === 'boolean') {
    const slug = asString(agentAccess.slug) || asString(rbac.agent_slug);
    if (slug) rows.push({
      kind: 'Агент', name: slug, allowed: agentAccess.allowed,
      reason: asString(agentAccess.reason) || (agentAccess.allowed ? 'Разрешён runtime RBAC' : 'Запрещён runtime RBAC'),
    });
  }
  add('Агент', rbac.allowed, true, 'Разрешён эффективной политикой');
  add('Агент', rbac.denied_by_rbac, false, 'Запрещён RBAC');
  add('Коллекция', collectionFilter.allowed, true, 'Доступна выбранному агенту');
  add('Коллекция', collectionFilter.denied_by_capability, false, 'Не входит в capability агента');
  add('Коллекция', collectionFilter.denied_by_rbac, false, 'Запрещена RBAC');
  const defaultCollectionAllow = typeof rbac.default_collection_allow === 'boolean'
    ? rbac.default_collection_allow
    : typeof collectionFilter.default_collection_allow === 'boolean' ? collectionFilter.default_collection_allow : undefined;
  return { rows: rows.sort((left, right) => `${left.kind}:${left.name}`.localeCompare(`${right.kind}:${right.name}`, 'ru')), defaultCollectionAllow };
}
const resultStatusOf = (value: unknown): TraceResultStatus => {
  const status = asString(value).toLowerCase();
  if (['completed', 'success', 'succeeded'].includes(status)) return 'completed';
  if (['failed', 'error'].includes(status)) return 'failed';
  if (status === 'unfulfillable') return 'unfulfillable';
  if (['aborted', 'cancelled', 'canceled'].includes(status)) return 'aborted';
  if (status === 'paused') return 'paused';
  if (['waiting', 'waiting_input', 'needs_dependency', 'confirmation_required', 'retry_scheduled'].includes(status)) return 'waiting';
  if (status === 'running' || status === 'in_progress') return 'running';
  return status ? 'running' : 'unknown';
};
export const traceResultStatusLabel = (status: TraceResultStatus): string => ({
  completed: 'Готово', failed: 'Ошибка', unfulfillable: 'Неисполнимо', aborted: 'Прервано', paused: 'На паузе',
  waiting: 'Ожидает данных', running: 'Выполняется', unknown: 'Нет результата',
} as Record<TraceResultStatus, string>)[status];
const isEndEvent = (type: string): boolean => type.endsWith('_end') || type.endsWith('_finished');
const iterationLabel = (type: string, number: number): string => {
  if (type === 'replan') return 'Перепланирование';
  if (type === 'checkpoint') return 'Контрольная точка';
  if (type === 'decision') return number > 1 ? 'Перепланирование' : 'Планирование';
  if (type === 'execution') return 'Исполнение';
  if (type === 'synthesis') return 'Подготовка ответа';
  if (type === 'extraction') return 'Извлечение фактов';
  if (type === 'preparation') return 'Подготовка';
  return type || 'Этап';
};
const executorKindFor = (slug: string): TraceExecutorKind => {
  if (slug === 'planner') return 'planner';
  if (slug === 'turn_preflight') return 'preflight';
  if (slug === 'memory_preparation' || slug === 'memory_selector') return 'memory_selector';
  if (slug === 'fact_extractor') return 'fact_extractor';
  if (slug === 'fact_compactor') return 'fact_compactor';
  if (slug === 'synthesizer') return 'synthesizer';
  return 'agent';
};
const stepKindFor = (stage: TraceStageKind, executor?: TraceExecutorRun): TraceStepKind => {
  if (stage === 'turn_preflight') return 'synthesis';
  if (stage === 'synthesis') return 'synthesis';
  if (stage === 'memory_preparation') return 'memory_selection';
  if (stage === 'memory_writeback') return 'memory_write';
  return executor?.kind === 'planner' ? 'planner_decision' : 'task_execution';
};
const tab = (id: TraceInspectorTabId, label: string): TraceInspectorTab => ({ id, label });
const hasResult = (result: TraceExecutorResult): boolean => (
  (result.status !== 'unknown' && result.status !== 'running')
  || result.output !== undefined
  || result.message !== undefined
  || result.operations.total > 0
  || result.needs !== undefined
  || result.artifacts !== undefined
);
const executorSnapshotTabs = (executor: TraceExecutorRun): TraceInspectorTab[] => [
  ...(executor.prompt ? [tab('prompt', 'Промпт')] : []),
  ...(executor.access ? [tab('rbac', 'Доступ')] : []),
  ...(executor.limits ? [tab('limits', 'Лимиты')] : []),
  ...(executor.toolOverrides ? [tab('operations', 'Операции')] : []),
  tab('raw', 'RAW'),
];
const callHasError = (call: TraceCall): boolean => (
  call.kind === 'error'
  || (call.kind === 'llm' && call.response !== undefined && llmResponseStatus(call.response.payload) === 'error')
  || (call.kind === 'tool' && toolResult(call.response?.payload ?? {}).success === false)
);
const isDocumentMemoryExecutor = (executor: TraceExecutorRun): boolean => executor.executorSlug === 'document_memory_extractor';
const isDocumentMemoryStage = (stage: TraceStage): boolean => stage.executorRuns.some(isDocumentMemoryExecutor);
export function tabsForTarget(target: TraceInspectionTarget): TraceInspectorTab[] {
  if (target.kind === 'stage' && target.stage.kind === 'route_policy') return [tab('info', 'Инфо'), tab('route_policy', 'Рекомендация'), tab('raw', 'RAW')];
  if (target.kind === 'stage' && isDocumentMemoryStage(target.stage)) return [tab('info', 'Инфо'), tab('result', 'Итог'), tab('raw', 'RAW')];
  if (target.kind === 'step' && isDocumentMemoryStage(target.step.stage)) return [tab('info', 'Инфо'), tab('result', 'Итог'), tab('raw', 'RAW')];
  if (target.kind === 'stage') return [tab('info', 'Инфо'), ...(target.stage.plan ? [tab('plan', 'План')] : []), ...(target.stage.executorRuns.some((item) => hasResult(item.result)) ? [tab('result', 'Результат')] : []), ...(target.stage.failure ? [tab('error', 'Ошибка')] : []), tab('raw', 'RAW')];
  if (target.kind === 'step') return [tab('info', 'Инфо'), tab('task', 'Задача'), ...(target.step.executorRuns.some((item) => hasResult(item.result)) ? [tab('result', 'Результат')] : []), tab('raw', 'RAW')];
  if (target.kind === 'executor') {
    if (target.executor.kind === 'route_policy') return [tab('info', 'Инфо'), tab('route_policy', 'Рекомендация'), tab('raw', 'RAW')];
    if (isDocumentMemoryExecutor(target.executor)) return [tab('info', 'Инфо'), tab('result', 'Итог'), tab('raw', 'RAW')];
    if (target.executor.executorSlug === 'checkpoint') return [tab('info', 'Инфо'), tab('checkpoint', 'Решение'), tab('raw', 'RAW')];
    const primary = target.executor.kind === 'planner'
      ? target.stage.plan ? [tab('plan', 'План')] : (hasResult(target.executor.result) ? [tab('result', 'Результат')] : [])
      : target.executor.kind === 'preflight' ? [tab('result', 'Маршрут')]
      : target.executor.kind === 'synthesizer' ? (hasResult(target.executor.result) ? [tab('result', 'Результат')] : [])
        : target.executor.kind === 'memory_selector' ? [tab('task', 'Задача')]
          : target.executor.kind === 'fact_extractor' ? [tab('task', 'Задача'), ...(target.executor.memoryResult ? [tab('facts', 'Кандидаты')] : [])]
              : target.executor.kind === 'fact_compactor' ? [tab('task', 'Задача'), ...(target.executor.memoryResult ? [tab('facts', 'Решения')] : []), ...(target.executor.memoryResult?.decisions.some((item) => item.outcome === 'published') ? [tab('published', 'Опубликовано')] : [])]
              : [tab('task', 'Задача'), ...(hasResult(target.executor.result) ? [tab('result', 'Результат')] : [])];
    return [tab('info', 'Инфо'), ...primary,
      ...(target.executor.kind === 'planner' && target.executor.input ? [tab('input', 'Вход')] : []),
      ...(target.executor.memoryContext ? [tab('memory', 'Память')] : []), ...executorSnapshotTabs(target.executor)];
  }
  if (target.kind === 'error') return [tab('info', 'Инфо'), tab('error', 'Ошибка'), tab('raw', 'RAW')];
  const hasError = callHasError(target.call);
  return [tab('info', 'Инфо'), tab('request', 'Запрос'), ...(target.call.requestView.toolName !== 'memory.search' && memoryContextFromTool(target.call) ? [tab('memory', 'Память')] : []), ...(hasError ? [tab('error', 'Ошибка')] : target.call.responseView ? [tab('response', 'Ответ')] : []), tab('raw', 'RAW')];
}

export function withTraceInspectorTabs(target: TraceInspectionTarget): TraceInspectionTarget {
  return { ...target, tabs: tabsForTarget(target) };
}
const eventsFor = (state: SandboxTraceState, entity: TraceEntity): RuntimeJournalEvent[] => (
  entity.eventIds.map((id) => state.eventsById[id]).filter((event): event is RuntimeJournalEvent => Boolean(event))
);
const startFor = (state: SandboxTraceState, entity: TraceEntity): RuntimeJournalEvent | undefined => (
  eventsFor(state, entity).find((event) => event.event_type.endsWith('_start') || event.event_type.endsWith('_started'))
);

function memoryComponentResult(events: RuntimeJournalEvent[]): TraceMemoryComponentResult | undefined {
  const resultEvent = [...events].reverse().find((event) => (
    event.event_type === 'memory_component_result'
    || (event.event_type === 'status' && event.payload.stage === 'memory_component_result')
  ));
  if (!resultEvent) return undefined;
  const payload = resultEvent.payload;
  const componentName = asString(payload.component_name);
  if (componentName !== 'fact_extractor' && componentName !== 'fact_compactor') return undefined;
  const sourceFacts = Array.isArray(payload.facts)
    ? payload.facts
    : ([...events].reverse().find((event) => event.event_type === 'memory_facts_result')?.payload.facts ?? []);
  const facts = Array.isArray(sourceFacts) ? sourceFacts.flatMap((item): TraceMemoryFact[] => {
    const fact = asRecord(item);
    if (!fact) return [];
    const subject = asString(fact.subject);
    const value = asString(fact.value);
    if (!subject || !value) return [];
    return [{
      scope: asString(fact.scope) || 'unknown',
      kind: asString(fact.kind) || 'fact',
      subject,
      value,
      confidence: asNumber(fact.confidence),
      changeType: asString(fact.change_type) || (componentName === 'fact_extractor' ? 'candidate_extracted' : 'candidate_reinforced'),
      statusBefore: asString(fact.status_before) || undefined,
      statusAfter: asString(fact.status_after) || asString(fact.status) || undefined,
      supportBefore: asNumber(fact.support_before),
      supportAfter: asNumber(fact.support_after) ?? asNumber(fact.support_count),
      supportDelta: asNumber(fact.support_delta),
      compactionAction: asString(fact.compaction_action) || undefined,
      decisionReason: asString(fact.decision_reason) || undefined,
    }];
  }) : [];
  const decisions = events.flatMap((event): TraceMemoryDecision[] => {
    if (event.event_type !== 'status' || event.payload.stage !== 'memory_candidate_decision') return [];
    const decision = event.payload;
    if (asString(decision.component_name) !== componentName) return [];
    const candidate = asRecord(decision.candidate);
    const evidence = asRecord(decision.evidence);
    const transition = asRecord(decision.transition);
    const subject = asString(candidate?.subject);
    const value = asString(candidate?.value);
    const fact = subject && value ? {
      scope: asString(candidate?.scope) || 'unknown',
      kind: asString(candidate?.kind) || 'fact', subject, value,
      confidence: asNumber(candidate?.confidence),
      changeType: asString(decision.reason_code) || 'memory_decision',
      statusBefore: asString(transition?.status_before) || undefined,
      statusAfter: asString(transition?.status_after) || undefined,
      supportBefore: asNumber(transition?.support_before),
      supportAfter: asNumber(transition?.support_after),
      supportDelta: asNumber(transition?.support_delta),
      compactionAction: asString(decision.action) || undefined,
    } satisfies TraceMemoryFact : undefined;
    return [{
      phase: asString(decision.decision_phase) || 'unknown',
      outcome: asString(decision.outcome) || 'unknown',
      reasonCode: asString(decision.reason_code) || 'unknown',
      candidateIds: Array.isArray(decision.candidate_ids) ? decision.candidate_ids.filter((item): item is string => typeof item === 'string') : [],
      fact, action: asString(decision.action) || undefined,
      evidenceCount: asNumber(evidence?.count),
    }];
  });
  return {
    componentName,
    status: asString(payload.status) || 'completed',
    insertedCount: asNumber(payload.inserted_count) ?? 0,
    updatedCount: asNumber(payload.updated_count) ?? 0,
    skippedCount: asNumber(payload.skipped_count) ?? 0,
    facts,
    decisions,
    errorCode: asString(payload.error_code) || undefined,
    errorMessage: asString(payload.error_message) || undefined,
    decisionCounts: asRecord(payload.decision_counts) ? Object.fromEntries(Object.entries(asRecord(payload.decision_counts)!).flatMap(([key, value]) => typeof value === 'number' ? [[key, value]] : [])) : {},
    durationMs: asNumber(payload.duration_ms),
  };
}

const memoryOperations = new Set(['memory.search', 'memory.lookup']);

export function memoryContextFromTool(call: TraceCall): TraceMemoryContext | undefined {
  if (!memoryOperations.has(call.requestView.toolName ?? '') || call.responseView?.toolResult?.success === false) return undefined;
  const data = asRecord(call.responseView?.toolResult?.data);
  return data ? memoryContextFromPayload({ memory_context: data, search_scope: data.search_scope }) : undefined;
}

function memoryContextFor(events: RuntimeJournalEvent[], calls: TraceCall[] = []): TraceMemoryContext | undefined {
  const payload = [...events].reverse().find((event) => (
    event.event_type === 'status' && ['memory_context_prepared', 'memory_context_used'].includes(asString(event.payload.stage))
  ))?.payload;
  const recalled = calls.flatMap((call) => memoryContextFromTool(call) ?? []);
  if (!payload && !recalled.length) return undefined;
  const base = memoryContextFromPayload(payload ?? { memory_context: [] });
  // Current executors record their actual accumulated memory after every search.
  // Rebuilding it from child calls would reintroduce duplicates and stale finds.
  if (payload?.memory_owner) return base;
  const context = [...base.context, ...recalled.flatMap((item) => item.context)];
  const unique = context.filter((item, index) => context.findIndex((other) => JSON.stringify(other) === JSON.stringify(item)) === index);
  return {
    ...base, context: unique,
    selectedFacts: Math.max(base.selectedFacts, unique.filter((item) => item.type === 'fact').length),
    selectedProjects: Math.max(base.selectedProjects, unique.filter((item) => item.type === 'project').length),
    selectedGlossary: Math.max(base.selectedGlossary, unique.filter((item) => item.type === 'glossary').length),
    selectedMemoryItems: Math.max(base.selectedMemoryItems, unique.filter((item) => item.type === 'knowledge').length),
    ambiguities: [...new Set([...base.ambiguities, ...recalled.flatMap((item) => item.ambiguities)])],
    sourceCheckReasons: [...new Set([...base.sourceCheckReasons, ...recalled.flatMap((item) => item.sourceCheckReasons)])],
  };
}

/** Project the recorded executor input and canonical memory operation results. */
export function memoryContextFromPayload(payload: Record<string, unknown>): TraceMemoryContext {
  const rawContext = payload.memory_context;
  const collect = (value: unknown): Record<string, unknown>[] => {
    if (Array.isArray(value)) return value.flatMap(collect);
    const record = asRecord(value);
    if (!record) return [];
    if (record.result || record.memory_context) return collect(record.result ?? record.memory_context);
    if (Array.isArray(record.groups)) return record.groups.flatMap(collect);
    const field = (key: string, type: string) => Array.isArray(record[key])
      ? (record[key] as unknown[]).flatMap((item) => asRecord(item) ? [{ ...asRecord(item), type }] : []) : [];
    if (record.type === 'fact' || (!record.type && record.scope && record.subject && record.value !== undefined)) return [{ ...record, type: 'fact' }];
    if (['project', 'glossary', 'knowledge', 'company_knowledge', 'project_knowledge'].includes(asString(record.type))) return [record];
    return [
      ...field('durable_facts', 'fact'), ...field('facts', 'fact'),
      ...field('relevant_projects', 'project'), ...field('projects', 'project'),
      ...field('resolved_terms', 'glossary'), ...field('glossary', 'glossary'),
      ...['relevant_knowledge', 'applicable_rules', 'applicable_procedures', 'known_constraints', 'items'].flatMap((key) => field(key, 'knowledge')),
    ];
  };
  const metadata = (value: unknown, key: string): string[] => {
    if (Array.isArray(value)) return value.flatMap((item) => metadata(item, key));
    const record = asRecord(value);
    return record ? [...stringArray(record[key]), ...metadata(record.result ?? record.memory_context, key)] : [];
  };
  const contextItems = collect(rawContext);
  const rawMemoryPayload = asRecord(rawContext);
  const context = contextItems.flatMap((item): TraceMemoryContextItem[] => {
    const record = asRecord(item);
    const type = asString(record?.type);
    if (type === 'fact') {
      const scope = asString(record?.scope) || 'unknown';
      const subject = asString(record?.subject);
      const value = asString(record?.value);
      return scope && subject && value ? [{ type: 'fact', scope, subject, value }] : [];
    }
    if (type === 'project') {
      const key = asString(record?.key);
      const name = asString(record?.name);
      return key && name ? [{ type: 'project', projectId: asString(record?.project_id) || undefined, key, name, matchedAliases: stringArray(record?.matched_aliases) }] : [];
    }
    if (type === 'glossary') {
      const term = asString(record?.term);
      const description = asString(record?.description) || asString(record?.definition);
      return term ? [{ type: 'glossary', scope: asString(record?.scope) || 'global', term, description, aliases: stringArray(record?.aliases) }] : [];
    }
    if (['knowledge', 'company_knowledge', 'project_knowledge'].includes(type)) {
      const source = asRecord(record?.metadata);
      const subject = asString(record?.subject) || asString(source?.document_title) || asString(source?.filename) || 'Фрагмент документа';
      const content = record?.content;
      const value = asString(record?.text) || asString(record?.value) || (content ? JSON.stringify(content) : '');
      return subject && value ? [{ type: 'knowledge', scope: asString(record?.scope_slug) || asString(record?.scope) || 'unknown', kind: asString(record?.kind) || 'knowledge', subject, value, confidence: asNumber(record?.confidence), sourceReferences: Array.isArray(record?.source_references) ? record.source_references : Array.isArray(source?.source_refs) ? source.source_refs : [], raw: record ?? undefined }] : [];
    }
    return [];
  });
  const scopeGroups = new Map<string, { scope: string; status: string; count: number; error?: string }>();
  const visitGroups = (value: unknown): void => {
    if (Array.isArray(value)) { value.forEach(visitGroups); return; }
    const record = asRecord(value);
    if (!record) return;
    if (record.result || record.memory_context) { visitGroups(record.result ?? record.memory_context); return; }
    if (Array.isArray(record.groups)) record.groups.forEach(group => {
      const row = asRecord(group);
      const scope = asString(row?.scope_slug);
      if (scope) scopeGroups.set(scope, { scope, status: asString(row?.status), count: asNumber(row?.count) ?? 0, error: asString(row?.error) || undefined });
    });
  };
  visitGroups(rawContext);
  return {
    ...(payload.memory_owner ? { owner: { kind: asString(payload.memory_owner), id: asString(payload.memory_owner_id) } } : {}),
    ...(scopeGroups.size ? { scopeGroups: [...scopeGroups.values()] } : {}),
    fallback: payload.fallback === true,
    selectedFacts: asNumber(payload.selected_facts) ?? context.filter((item) => item.type === 'fact').length,
    selectedProjects: asNumber(payload.selected_projects) ?? context.filter((item) => item.type === 'project').length,
    selectedGlossary: asNumber(payload.selected_glossary) ?? context.filter((item) => item.type === 'glossary').length,
    selectedMemoryItems: asNumber(payload.selected_memory_items) ?? context.filter((item) => item.type === 'knowledge').length,
    context,
    ambiguities: [...new Set([...stringArray(payload.ambiguities), ...metadata(rawContext, 'uncertainties'), ...metadata(rawContext, 'ambiguities')])],
    sourceCheckReasons: [...new Set([...stringArray(payload.source_check_reasons), ...metadata(rawContext, 'rag_reasons')])],
    ...(Array.isArray(payload.scope_candidates) ? { scopeCandidates: payload.scope_candidates } : Array.isArray(rawMemoryPayload?.scope_candidates) ? { scopeCandidates: rawMemoryPayload.scope_candidates } : {}),
    ...(Array.isArray(payload.scope_ambiguities) ? { scopeAmbiguities: payload.scope_ambiguities } : Array.isArray(rawMemoryPayload?.scope_ambiguities) ? { scopeAmbiguities: rawMemoryPayload.scope_ambiguities } : {}),
    ...((payload.scope_candidates_truncated === true || rawMemoryPayload?.scope_candidates_truncated === true) ? { truncated: true } : {}),
    ...(asRecord(payload.search_scope) ? { searchScope: asRecord(payload.search_scope) } : {}),
  };
}

function extractionResultFor(entity: TraceEntity, start: RuntimeJournalEvent | undefined, end: RuntimeJournalEvent | undefined): TraceExtractionResult {
  const payload = { ...(asRecord(start?.payload) ?? {}), ...(asRecord(end?.payload) ?? {}) };
  const failed = entity.status === 'failed' || end?.event_type === 'extraction_failed';
  return {
    status: failed ? 'failed' : end ? 'completed' : 'running',
    fileName: asString(payload.file_name) || asString(payload.filename) || undefined,
    parser: asString(payload.parser) || undefined,
    contentType: asString(payload.content_type) || undefined,
    contentKind: asString(payload.content_kind) || undefined,
    format: asString(payload.format) || undefined,
    profile: asString(payload.profile) || undefined,
    representation: asString(payload.representation) || undefined,
    truncated: typeof payload.truncated === 'boolean' ? payload.truncated : undefined,
    warnings: stringArray(payload.warnings),
    outputChars: asNumber(payload.output_chars),
    durationMs: asNumber(payload.duration_ms),
    message: asString(payload.safe_message) || asString(payload.user_message) || asString(payload.message) || asString(payload.error) || undefined,
  };
}

function latestPayload(events: RuntimeJournalEvent[], eventType: string): Record<string, unknown> | undefined {
  return [...events].reverse().find((event) => event.event_type === eventType)?.payload;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];
}

function preflightFor(state: SandboxTraceState, executor: TraceEntity): TracePreflight | undefined {
  const entity = executor.childKeys
    .map((key) => state.entitiesByKey[key])
    .find((child): child is TraceEntity => Boolean(child) && child.type === 'preflight');
  if (!entity) return undefined;
  const events = eventsFor(state, entity);
  const payload = latestPayload(events, 'preflight_completed')
    ?? latestPayload(events, 'preflight_failed')
    ?? latestPayload(events, 'preflight_snapshot')
    ?? latestPayload(events, 'preflight_started')
    ?? {};
  const missing = asRecord(payload.missing) ?? {};
  return {
    status: asString(payload.status) || entity.status || 'unknown',
    mode: asString(payload.mode) || undefined,
    durationMs: asNumber(payload.duration_ms),
    missing: {
      tools: stringArray(missing.tools),
      collections: stringArray(missing.collections),
      credentials: stringArray(missing.credentials),
    },
    operationsCount: asNumber(payload.operations_count),
    dataInstancesCount: asNumber(payload.data_instances_count),
    // Access decisions have their own inspector tab; do not repeat them in validation.
  };
}

function routeFor(calls: TraceCall[], ownerEvents: RuntimeJournalEvent[] = []): TraceRoute | undefined {
  const call = [...calls].reverse().find((item) => item.kind === 'llm' && item.response);
  const response = asRecord(parseCallContent(llmResponseContent(call?.response?.payload ?? {})).data) ?? {};
  const brief = asRecord(response.task_brief) ?? {};
  const routeDecision = [...ownerEvents].reverse().find((event) => event.event_type === 'preflight_route_decision')?.payload;
  const decision = asRecord(routeDecision) ?? {};
  const proposed = asString(decision.proposed_route) || undefined;
  const effective = asString(decision.effective_route) || undefined;
  if (!call?.response && !routeDecision) return undefined;
  const requestMessage = call?.request.payload.messages;
  const userMessage = Array.isArray(requestMessage)
    ? requestMessage.map((item) => asRecord(item) ?? {}).find((item) => item.role === 'user')?.content
    : undefined;
  let input: unknown;
  if (userMessage !== undefined) {
    const parsed = parseCallContent(userMessage);
    input = sanitizeDisplay(parsed.data ?? parsed.text);
  }
  if (!proposed && !effective && Object.keys(brief).length === 0 && input === undefined) return undefined;
  return {
    proposed,
    effective,
    reason: ['model_selected', 'runtime_reroute', 'policy_route'].includes(asString(decision.reason))
      ? asString(decision.reason) as TraceRoute['reason'] : undefined,
    detail: asString(decision.detail) || undefined,
    policyRecommendationId: asString(decision.policy_recommendation_id) || undefined,
    policyDisposition: ['accepted', 'modified', 'rejected', 'not_applicable'].includes(asString(decision.policy_disposition))
      ? asString(decision.policy_disposition) as TraceRoute['policyDisposition'] : undefined,
    policyReasonCode: asString(decision.reason_code) || undefined,
    goal: asString(brief.goal),
    direction: asString(brief.direction),
    expectedResult: asString(brief.expected_result),
    entityHints: stringArray(brief.entity_hints),
    projectHints: stringArray(brief.project_hints),
    constraints: stringArray(brief.constraints),
    input,
  };
}

function promptFor(events: RuntimeJournalEvent[], calls: TraceCall[]): TracePrompt | undefined {
  const snapshot = [...events].reverse().map((event) => event.payload)
    .map((payload) => payload.config_snapshot ?? payload.context_snapshot)
    .find((value) => {
      const record = asRecord(value) ?? {};
      return record.system_prompt !== undefined || record.system_prompt_hash !== undefined;
    });
  const snapshotRecord = asRecord(snapshot) ?? {};
  const text = asString(snapshotRecord.system_prompt);
  const hash = asString(snapshotRecord.system_prompt_hash);
  if (text || hash) return { text: text || undefined, hash: hash || undefined };

  for (const call of calls) {
    if (call.kind !== 'llm') continue;
    const messages = Array.isArray(call.request.payload.messages) ? call.request.payload.messages : [];
    const systemMessage = messages.find((message) => {
      const record = asRecord(message) ?? {};
      return record.role === 'system' && typeof record.content === 'string';
    });
    const prompt = asString((asRecord(systemMessage) ?? {}).content);
    if (prompt) return { text: prompt };
  }
  return undefined;
}

function toolOverridesFor(events: RuntimeJournalEvent[]): TraceToolOverrideSnapshot | undefined {
  const payload = [...events].reverse().find((event) => event.event_type === 'sandbox_override_snapshot')?.payload;
  if (!payload) return undefined;
  const configured = asRecord(payload.configured) ?? {};
  const publication = asRecord(configured.publication) ?? {};
  const semantics = asRecord(configured.semantics) ?? {};
  const configuredPublication = Object.fromEntries(Object.entries(publication)
    .filter((entry): entry is [string, boolean] => typeof entry[1] === 'boolean'));
  const configuredSemantics = Object.fromEntries(Object.entries(semantics));
  const effectiveOperations = (Array.isArray(payload.effective_operations) ? payload.effective_operations : [])
    .flatMap((item): TraceToolOverrideSnapshot['effectiveOperations'] => {
      const row = asRecord(item) ?? {};
      const toolId = asString(row.discovered_tool_id);
      return toolId ? [{
        toolId,
        publicationConfigured: typeof row.publication_configured === 'boolean' ? row.publication_configured : undefined,
        publishedEffective: typeof row.published_effective === 'boolean' ? row.published_effective : undefined,
        configuredSemantics: row.configured,
        effectiveSemantics: row.effective,
      }] : [];
    });
  const suppressed = asRecord(payload.suppressed_publication) ?? {};
  const suppressedPublication = Object.entries(suppressed).flatMap(([toolId, reason]) => toolId
    ? [{ toolId, reason: asString(reason) || undefined }] : []);
  if (!Object.keys(configuredPublication).length && !Object.keys(configuredSemantics).length
    && !effectiveOperations.length && !suppressedPublication.length) return undefined;
  return { configuredPublication, configuredSemantics, effectiveOperations, suppressedPublication };
}

function metricsFor(state: SandboxTraceState, entity: TraceEntity): TraceMetrics {
  const events = eventsFor(state, entity);
  const started = startFor(state, entity);
  const ended = [...events].reverse().find((event) => event.event_type.endsWith('_end') || event.event_type.endsWith('_finished'));
  const elapsedMs = ended?.duration_ms ?? (
    started && ended ? new Date(ended.occurred_at).getTime() - new Date(started.occurred_at).getTime() : undefined
  );
  let tokens: number | undefined;
  let retries = 0;
  let calls = 0;
  let successfulCalls = 0;
  let failedCalls = 0;
  for (const event of events) {
    const usage = asRecord(event.payload.usage) ?? asRecord(event.payload.token_usage) ?? {};
    const total = asNumber(event.payload.tokens_total) ?? asNumber(usage.total_tokens) ?? asNumber(event.payload.tokens);
    if (total !== undefined) tokens = Math.max(tokens ?? 0, total);
    if (event.event_type === 'llm_response' && event.payload.terminal !== false) {
      calls += 1;
      if (llmResponseStatus(event.payload) === 'error') failedCalls += 1;
      else successfulCalls += 1;
    }
    if (event.event_type === 'tool_result') {
      const success = toolResult(event.payload).success;
      if (success !== undefined) {
        calls += 1;
        if (success) successfulCalls += 1;
        else failedCalls += 1;
      }
    }
  }
  retries = events.filter((event) => event.event_type === 'protocol_retry').length;
  return {
    elapsedMs: elapsedMs && elapsedMs > 0 ? elapsedMs : undefined,
    tokens,
    retries: retries || undefined,
    calls: calls || undefined,
    successfulCalls: successfulCalls || undefined,
    failedCalls: failedCalls || undefined,
  };
}

function aggregateMetrics(own: TraceMetrics, children: TraceMetrics[]): TraceMetrics {
  const sum = (key: keyof TraceMetrics): number | undefined => {
    const values = [own, ...children]
      .map((item) => item[key])
      .filter((value): value is number => value !== undefined);
    return values.length ? values.reduce((total, value) => total + value, 0) : undefined;
  };
  const childElapsed = children
    .map((item) => item.elapsedMs)
    .filter((value): value is number => value !== undefined);
  return {
    elapsedMs: own.elapsedMs ?? (childElapsed.length ? childElapsed.reduce((total, value) => total + value, 0) : undefined),
    tokens: sum('tokens'),
    retries: sum('retries'),
    calls: sum('calls'),
    successfulCalls: sum('successfulCalls'),
    failedCalls: sum('failedCalls'),
  };
}

function numberPayload(payload: Record<string, unknown>, key: string): number | undefined {
  return asNumber(payload[key]);
}

function requestViewFor(kind: TraceCallKind, payload: Record<string, unknown>): TraceCallRequest {
  const rawMessages = Array.isArray(payload.messages) ? payload.messages : [];
  const messages = rawMessages
    .map((item) => {
      const message = asRecord(item) ?? {};
      return { role: asString(message.role) || 'message', content: parseCallContent(message.content ?? message) };
    });
  return {
    model: asString(payload.model) || undefined,
    purpose: asString(payload.purpose) ? purposeLabel(payload.purpose) : undefined,
    temperature: numberPayload(payload, 'temperature'),
    maxTokens: numberPayload(payload, 'max_tokens'),
    requestBytes: numberPayload(payload, 'request_bytes'),
    inputTokensEstimate: numberPayload(payload, 'input_tokens_estimate'),
    responseSchemaBytes: numberPayload(payload, 'response_schema_bytes'),
    messages,
    nativeToolCalls: messages.flatMap((_message, index) => {
      const raw = asRecord(rawMessages[index]);
      return Array.isArray(raw?.tool_calls) ? raw.tool_calls : [];
    }),
    tools: Array.isArray(payload.tools) ? payload.tools : undefined,
    responseSchema: payload.response_schema ?? payload.json_schema,
    messageTranscript: messageTranscript(messages),
    toolName: asString(payload.tool) || asString(payload.tool_slug) || undefined,
    description: asString(payload.description) || asString(payload.intent) || undefined,
    arguments: payload.arguments,
    question: asString(payload.question) || undefined,
    message: asString(payload.message) || undefined,
  };
}

function messageTranscript(messages: Array<{ role: string; content: ParsedContent }>): string | undefined {
  if (!messages.length) return undefined;
  const labels: Record<string, string> = {
    system: 'Системные инструкции',
    user: 'Запрос пользователя',
    assistant: 'Ответ ассистента',
    tool: 'Контекст инструмента',
  };
  return messages.map((message) => {
    const content = message.content.kind === 'text'
      ? message.content.text ?? ''
      : JSON.stringify(message.content.data, null, 2);
    return `${labels[message.role] ?? `Сообщение: ${message.role}`}\n${'─'.repeat(24)}\n${content}`;
  }).join('\n\n');
}

function toolResultSummary(success: boolean | undefined, data: unknown): string {
  const record = asRecord(data) ?? {};
  const total = asNumber(record.total) ?? asNumber(record.count);
  if (total !== undefined) return `Получено: ${total}`;
  if (Array.isArray(data)) return `Получено элементов: ${data.length}`;
  if (Object.keys(record).length) return `Получено полей: ${Object.keys(record).length}`;
  return success === false ? 'Операция завершилась ошибкой' : 'Операция выполнена';
}

function responseViewFor(
  kind: TraceCallKind,
  response: RuntimeJournalEvent | undefined,
  linkedToolCalls: RuntimeJournalEvent[],
): TraceCallResponse | undefined {
  if (!response) return undefined;
  const payload = response.payload;
  const content = kind === 'llm' ? llmResponseContent(payload) : undefined;
  const parsed = content === undefined ? undefined : parseCallContent(content);
  const parsedRecord = parsed?.kind === 'json' || parsed?.kind === 'tool_call' ? asRecord(parsed.data) : undefined;
  const toolCall = parsed && parsedRecord && ('tool' in parsedRecord || 'arguments' in parsedRecord)
    ? { name: asString(parsedRecord.tool) || 'Операция', arguments: parsedRecord.arguments }
    : undefined;
  const toolResultView = kind === 'tool'
    ? (() => {
      const result = toolResult(payload);
      return {
        success: result.success,
        message: result.message,
        data: sanitizeDisplay(result.data),
        summary: toolResultSummary(result.success, result.data),
        truncated: payload.truncated === true,
      };
    })()
    : undefined;
  const interactionResponse = kind === 'clarify' || kind === 'confirm'
    ? payload.response ?? payload.user_answer ?? payload.answer
    : undefined;
  return {
    resultKind: asString(payload.result_kind) || undefined,
    responseLength: numberPayload(payload, 'response_length'),
    terminal: typeof payload.terminal === 'boolean' ? payload.terminal : undefined,
    content: parsed,
    ...(interactionResponse !== undefined ? { content: parseCallContent(interactionResponse) } : {}),
    toolCall,
    linkedToolCalls: linkedToolCalls.map((event) => ({
      name: asString(event.payload.tool) || 'Операция',
      arguments: event.payload.arguments,
    })),
    toolResult: toolResultView,
  };
}

function callFor(state: SandboxTraceState, entity: TraceEntity): TraceCall | null {
  const isLlm = entity.type === 'llm_call';
  const isTool = entity.type === 'tool_call';
  const isInteraction = entity.type === 'question_answer' || entity.type === 'interaction' || entity.type === 'dialog';
  const isError = entity.type === 'error';
  if (!isLlm && !isTool && !isInteraction && !isError) return null;
  const events = eventsFor(state, entity);
  const requestEvents = events.filter((event) => (
    isLlm ? event.event_type === 'llm_request' :
      isTool ? event.event_type === 'tool_call' :
        isError ? event.event_type === 'error' :
          event.event_type === 'waiting_input' || event.event_type === 'confirmation_required' || event.event_type === 'question_answer'
  ));
  const request = isLlm ? requestEvents[requestEvents.length - 1] : requestEvents[0];
  if (!request) return null;
  // A retry-chain may intentionally reuse one llm_call entity.  The latest
  // response is the terminal state of that user-visible request; selecting
  // the first response would keep a recovered call red after a retry.
  const response = [...events].reverse().find((event) => (
    isLlm ? event.event_type === 'llm_response' :
      isTool ? event.event_type === 'tool_result' :
        event.event_type === 'question_answer' && event.id !== request.id
  ));
  const interactionKind = request.event_type === 'confirmation_required' ? 'confirm' : 'clarify';
  const toolCallCount = isLlm
    ? Object.values(state.eventsById).filter((event) => (
      event.event_type === 'tool_call'
      && asString(event.payload.llm_call_id) === entity.id
    )).length
    : undefined;
  const logicalLlmCallId = isLlm ? asString(request.payload.logical_llm_call_id) || undefined : undefined;
  const retryEvents = (isLlm || isTool)
    ? state.eventIdsBySequence
      .map((id) => state.eventsById[id])
      .filter((event) => event.event_type === 'protocol_retry'
        && (asString(event.payload.llm_call_id) === entity.id
          || (isLlm && asString(event.entity_id) === entity.id)
          || (isTool && asString(event.entity_id ?? event.payload.entity_id) === entity.id)))
    : [];
  const linkedToolCalls = isLlm
    ? Object.values(state.eventsById)
      .filter((event) => event.event_type === 'tool_call'
        && asString(event.payload.llm_call_id) === entity.id)
      .sort((left, right) => left.sequence - right.sequence)
    : [];
  const extractionEntity = isTool
    ? entity.childKeys.map((key) => state.entitiesByKey[key]).find((child): child is TraceEntity => Boolean(child) && child.type === 'extraction')
    : undefined;
  const extraction = extractionEntity ? (() => {
    const extractionEvents = eventsFor(state, extractionEntity);
    return {
      entity: extractionEntity,
      events: extractionEvents,
      start: extractionEvents.find((event) => event.event_type === 'extraction_started'),
      end: [...extractionEvents].reverse().find((event) => event.event_type === 'extraction_completed' || event.event_type === 'extraction_failed'),
      result: extractionResultFor(
        extractionEntity,
        extractionEvents.find((event) => event.event_type === 'extraction_started'),
        [...extractionEvents].reverse().find((event) => event.event_type === 'extraction_completed' || event.event_type === 'extraction_failed'),
      ),
    } satisfies TraceExtraction;
  })() : undefined;
  const plan = isLlm && response && llmOutcome(response.payload, toolCallCount ?? 0).kind === 'plan'
    ? projectPlan(llmResponseContent(response.payload))
    : undefined;
  const call = {
    entity,
    events,
    request,
    response,
    retryEvents,
    linkedToolCalls,
    kind: isLlm ? 'llm' : isTool ? 'tool' : isError ? 'error' : interactionKind,
    title: isLlm
      ? (asString(request.payload.purpose) ? purposeLabel(request.payload.purpose) : asString(request.payload.model) || 'LLM')
      : isTool
        ? callDisplayName(asString(request.payload.tool) || 'Tool')
        : isError
          ? asString(request.payload.error) || asString(request.payload.message) || 'Ошибка'
          : asString(request.payload.question)
            || asString(request.payload.message)
            || asString(request.payload.summary)
            || asString(request.payload.operation)
            || asString(request.payload.tool_slug)
            || (interactionKind === 'confirm' ? 'Подтверждение операции' : 'Уточнение'),
    summary: isTool && response
      ? (() => {
          const result = toolResult(response.payload);
          if (result.message) return result.message;
          const data = result.data && typeof result.data === 'object' ? result.data as Record<string, unknown> : null;
          if (typeof data?.total === 'number') return `${data.total} результатов`;
          if (typeof data?.field_count === 'number') return `Полей: ${data.field_count}`;
          return undefined;
        })()
      : undefined,
    toolCallCount,
    extraction,
    plan,
    logicalLlmCallId,
  } as TraceCall;
  const presentation = callPresentation(call);
  call.info = {
    status: presentation.status,
    durationMs: presentation.durationMs,
    retryCount: presentation.retryCount,
    outcome: presentation.outcome,
    tokensIn: presentation.tokensIn,
    tokensOut: presentation.tokensOut,
    tokensTotal: presentation.tokensTotal,
  };
  call.requestView = requestViewFor(call.kind, request.payload);
  call.responseView = responseViewFor(call.kind, response, linkedToolCalls);
  call.errorView = presentation.error;
  return call;
}

/**
 * Collapse only historical retry chains that the runtime explicitly
 * correlated. Current runtime retries already share one llm_call entity.
 */
function groupLogicalLlmCalls(calls: TraceCall[]): TraceCall[] {
  const groups = new Map<string, TraceCall[]>();
  const ordered: Array<TraceCall | string> = [];
  for (const call of calls) {
    if (call.kind !== 'llm' || !call.logicalLlmCallId) {
      ordered.push(call);
      continue;
    }
    const existing = groups.get(call.logicalLlmCallId);
    if (existing) {
      existing.push(call);
    } else {
      groups.set(call.logicalLlmCallId, [call]);
      ordered.push(call.logicalLlmCallId);
    }
  }
  return ordered.map((item) => {
    if (typeof item !== 'string') return item;
    const attempts = groups.get(item) ?? [];
    if (attempts.length <= 1) return attempts[0];
    const last = attempts[attempts.length - 1];
    const events = attempts.flatMap((attempt) => attempt.events);
    const retryEvents = attempts.flatMap((attempt) => attempt.retryEvents);
    const linkedToolCalls = attempts.flatMap((attempt) => attempt.linkedToolCalls);
    return {
      ...last,
      entity: attempts[0].entity,
      events,
      request: attempts[0].request,
      response: last.response,
      retryEvents,
      linkedToolCalls,
      toolCallCount: linkedToolCalls.length,
      attempts,
    } satisfies TraceCall;
  });
}

function syntheticCallEntity(event: RuntimeJournalEvent, type?: 'question_answer' | 'error'): TraceEntity {
  const entityType = asString(event.entity_type) || type || 'question_answer';
  const entityId = asString(event.entity_id) || event.id;
  return {
    key: `${entityType}:${entityId}`,
    type: entityType,
    id: entityId,
    parentKey: event.parent_entity_type && event.parent_entity_id
      ? `${event.parent_entity_type}:${event.parent_entity_id}`
      : null,
    childKeys: [],
    eventIds: [event.id],
    status: entityType === 'error' ? 'error' : 'waiting',
    snapshotsByKind: {},
  };
}

function directCallsFor(
  state: SandboxTraceState,
  executor: TraceEntity,
  iteration: TraceEntity,
  excludedEventIds: Set<string>,
): TraceCall[] {
  const executorEvents = eventsFor(state, executor);
  const startSequence = executorEvents.find((item) => item.event_type.endsWith('_start') || item.event_type.endsWith('_started'))?.sequence ?? -Infinity;
  const endSequence = executorEvents
    .filter((item) => isEndEvent(item.event_type))
    .map((item) => item.sequence)
    .sort((left, right) => left - right)[0];
  const events = Object.values(state.eventsById).filter((event) => {
    const parentId = asString(event.parent_entity_id ?? event.payload.parent_entity_id);
    const parentType = asString(event.parent_entity_type ?? event.payload.parent_entity_type);
    const belongsToExecutor = parentType === executor.type && parentId === executor.id;
    const hasNoParent = !parentType && !parentId;
    const isUnscopedCall = event.event_type === 'confirmation_required' || event.event_type === 'error';
    const belongsToActiveExecutor = hasNoParent
      && isUnscopedCall
      && event.sequence >= startSequence
      && (endSequence === undefined || event.sequence <= endSequence);
    const belongsToPlannerIteration = executor.id && executor.type === 'agent_execution'
      && asString(state.entitiesByKey[executor.parentKey ?? '']?.type) === 'planner_iteration'
      && parentType === iteration.type && parentId === iteration.id;
    return belongsToExecutor || belongsToActiveExecutor || belongsToPlannerIteration;
  });

  return events
    .filter((event) => event.event_type === 'llm_request'
      || event.event_type === 'tool_call'
      || event.event_type === 'waiting_input'
      || event.event_type === 'confirmation_required'
      || event.event_type === 'error')
    .filter((event) => !excludedEventIds.has(event.id))
    .map((event) => {
      const existing = event.entity_type && event.entity_id
        ? state.entitiesByKey[`${event.entity_type}:${event.entity_id}`]
        : undefined;
      return callFor(state, existing ?? {
        ...syntheticCallEntity(event, event.event_type === 'error' ? 'error' : 'question_answer'),
        parentKey: executor.key,
      });
    })
    .filter((call): call is TraceCall => Boolean(call));
}

function resultOutputFrom(payload: Record<string, unknown>): unknown {
  for (const key of ['output', 'result', 'answer', 'response', 'content', 'summary', 'message']) {
    if (payload[key] !== undefined && payload[key] !== null && payload[key] !== '') return payload[key];
  }
  return undefined;
}

function resultMessageFrom(payload: Record<string, unknown>): string | undefined {
  for (const key of ['user_message', 'safe_message', 'operator_message', 'message', 'error']) {
    const value = asString(payload[key]);
    if (value) return value;
  }
  return undefined;
}

function documentMemoryResult(events: RuntimeJournalEvent[]): Record<string, unknown> | undefined {
  const event = [...events].reverse().find((item) => (
    item.event_type === 'status' && typeof item.payload.stage === 'string'
      && item.payload.stage.startsWith('memory_')
  ));
  if (!event) return undefined;
  const payload = event.payload;
  const fields = [
    'stage', 'decision', 'document_kind', 'cursor', 'section_count', 'item_count',
    'section_ids', 'next_section', 'created', 'extended', 'rejected', 'candidates',
    'conflicts', 'duplicates', 'autoeligible', 'snapshot_status',
  ];
  const result = Object.fromEntries(fields
    .filter((key) => payload[key] !== undefined)
    .map((key) => [key, payload[key]]));
  return Object.keys(result).length ? result : undefined;
}

function executorResultFor(
  state: SandboxTraceState,
  entity: TraceEntity,
  executorName: string,
  executorSlug: string,
  calls: TraceCall[],
): TraceExecutorResult {
  const executorEvents = eventsFor(state, entity);
  const ended = [...executorEvents].reverse().find((event) => event.event_type === 'agent_end');
  const isSynthesizer = executorSlug === 'synthesizer';
  const final = isSynthesizer
    ? [...executorEvents].reverse().find((event) => event.event_type === 'final_answer_marker' || (event.event_type === 'status' && event.payload.stage === 'final_answer_marker'))
      ?? state.eventIdsBySequence
        .map((id) => state.eventsById[id])
        .filter((event): event is RuntimeJournalEvent => Boolean(event))
        .filter((event) => (event.event_type === 'final_answer_marker' || (event.event_type === 'status' && event.payload.stage === 'final_answer_marker'))
          && event.parent_entity_type === 'synthesis_run'
          && event.parent_entity_id === entity.id)
        .sort((left, right) => right.sequence - left.sequence)[0]
    : undefined;
  const error = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .find((event) => event?.event_type === 'error' && (
      event.payload.agent_execution_id === entity.id
      || (event.parent_entity_type === entity.type && event.parent_entity_id === entity.id)
    ));
  const endPayload = asRecord(ended?.payload) ?? {};
  const finalPayload = asRecord(final?.payload) ?? {};
  const errorPayload = asRecord(error?.payload) ?? {};
  const terminalResult = asRecord(endPayload.result) ?? {};
  const memoryOutput = executorSlug === 'document_memory_extractor'
    ? documentMemoryResult(executorEvents)
    : undefined;
  const resultPayload = isSynthesizer && Object.keys(finalPayload).length
    ? finalPayload : { ...finalPayload, ...terminalResult, ...endPayload };
  // Run completion is read only from the canonical final_answer_marker above.
  const parsedFinal = !isSynthesizer ? asRecord(parseCallContent(finalPayload.content).data) : undefined;
  const declaration = parsedFinal && ['fulfilled', 'needs', 'unfulfillable'].includes(asString(parsedFinal.completion))
    ? parsedFinal : undefined;
  let output = memoryOutput ?? resultOutputFrom(resultPayload);
  if (memoryOutput === undefined && declaration) {
    output = declaration.structured_response !== undefined && declaration.structured_response !== null
      ? declaration.structured_response : declaration.answer ?? declaration.structured_response;
  }
  const toolCalls = calls.filter((call) => call.kind === 'tool' && call.info.status !== 'running' && call.info.status !== 'waiting_retry');
  const succeeded = toolCalls.filter((call) => toolResult(call.response?.payload ?? {}).success === true).length;
  const failed = toolCalls.filter((call) => toolResult(call.response?.payload ?? {}).success === false).length;
  const outcome = resultPayload.outcome ?? resultPayload.completion;
  const lifecycleStatus = asString(resultPayload.status).toLowerCase();
  const statusValue = ['failed', 'error', 'aborted', 'cancelled', 'canceled', 'paused', 'waiting', 'waiting_input'].includes(lifecycleStatus)
    ? resultPayload.status : (outcome ?? resultPayload.status ?? entity.status);
  const status = resultStatusOf(error ? 'failed' : statusValue);
  return {
    name: executorName,
    status,
    statusLabel: traceResultStatusLabel(status),
    output: output === undefined ? undefined : sanitizeDisplay(parseCallContent(output).data ?? output),
    message: resultMessageFrom(errorPayload) ?? resultMessageFrom(resultPayload)
      ?? (asString(declaration?.answer) || undefined),
    completionKind: asString(endPayload.completion_kind) || undefined,
    sufficientForPhase: typeof endPayload.sufficient_for_phase === 'boolean' ? endPayload.sufficient_for_phase : undefined,
    missingInputs: endPayload.missing_inputs,
    needs: endPayload.needs ?? (Array.isArray(declaration?.needs) && declaration.needs.length ? declaration.needs : undefined),
    artifacts: endPayload.artifacts ?? endPayload.attachments ?? resultPayload.attachments ?? resultPayload.artifacts,
    sources: resultPayload.sources,
    operations: { total: toolCalls.length, succeeded, failed },
  };
}

function executorInfoFor(
  result: TraceExecutorResult,
  calls: TraceCall[],
  durationMs: number | undefined,
  limits?: TraceLimitsView,
): TraceExecutorInfoView {
  const limitByKey = new Map((limits?.rows ?? []).map((row) => [row.key, row]));
  const llmCalls = calls.filter((call) => call.kind === 'llm' && call.info.status !== 'running' && call.info.status !== 'waiting_retry');
  const toolCalls = calls.filter((call) => call.kind === 'tool' && call.info.status !== 'running' && call.info.status !== 'waiting_retry');
  const llmAttempts = llmCalls.flatMap((call) => call.attempts ?? [call]);
  const sum = (values: Array<number | undefined>): number | undefined => {
    const present = values.filter((value): value is number => value !== undefined);
    return present.length ? present.reduce((total, value) => total + value, 0) : undefined;
  };
  const tokensIn = sum(llmAttempts.map((call) => call.info.tokensIn));
  const tokensOut = sum(llmAttempts.map((call) => call.info.tokensOut));
  const tokensTotal = sum(llmAttempts.map((call) => call.info.tokensTotal));
  const statistics: TraceExecutorStatistic[] = [];
  const add = (key: TraceExecutorStatisticKey, label: string, value: number | undefined) => {
    if (value === undefined || value === 0) return;
    statistics.push({ key, label, value, limit: limitByKey.get(key) });
  };
  add('llm_calls', 'LLM-вызовы', llmCalls.length);
  add('tool_calls', 'Вызовы инструментов', toolCalls.length);
  add('tokens_in', 'Входные токены', tokensIn);
  add('tokens_out', 'Выходные токены', tokensOut);
  add('tokens_total', 'Всего токенов', tokensTotal);
  add('llm_retries', 'Повторы LLM', sum(llmCalls.map((call) => call.info.retryCount)));
  add('llm_errors', 'Ошибки LLM', llmCalls.filter((call) => call.info.status === 'error').length);
  add('tool_errors', 'Ошибки инструментов', toolCalls.filter((call) => call.info.status === 'error').length);
  return {
    status: result.status,
    statusLabel: result.statusLabel,
    durationMs,
    statistics,
  };
}

function executorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  if (entity.type !== 'agent_execution') return null;
  const start = startFor(state, entity);
  if (!start) return null;
  const payload = start.payload;
  const slug = asString(payload.agent_slug) || 'unknown';
  const executorType = (asString(payload.executor_type) || asString(payload.role) || 'agent').toUpperCase();
  const executorName = asString(payload.executor_name) || (slug === 'planner' ? 'Планер' : slug);
  const task = asString(payload.task_title) || asString(payload.task_objective) || 'Выполнение задачи';
  const childCalls = entity.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((child): child is TraceEntity => Boolean(child))
    .map((child) => callFor(state, child))
    .filter((call): call is TraceCall => Boolean(call));
  const childEventIds = new Set(entity.childKeys.flatMap((key) => state.entitiesByKey[key]?.eventIds ?? []));
  const iteration = entity.parentKey ? state.entitiesByKey[entity.parentKey] : undefined;
  const directCalls = iteration
    ? directCallsFor(state, entity, iteration, childEventIds)
    : directCallsFor(state, entity, entity, childEventIds);
  const calls = groupLogicalLlmCalls([...childCalls, ...directCalls]
    .sort((left, right) => left.request.sequence - right.request.sequence));
  const executorEvents = eventsFor(state, entity);
  const baseMetrics = metricsFor(state, entity);
  const callMetrics = calls.reduce((result, call) => {
    if (call.info.status === 'running' || call.info.status === 'waiting_retry') return result;
    const failed = call.kind === 'error'
      || (call.kind === 'llm' && call.response && llmResponseStatus(call.response.payload) === 'error')
      || (call.kind === 'tool' && call.response && toolResult(call.response.payload).success === false);
    return {
      calls: result.calls + 1,
      successfulCalls: result.successfulCalls + (call.response && !failed ? 1 : 0),
      failedCalls: result.failedCalls + (failed ? 1 : 0),
    };
  }, { calls: 0, successfulCalls: 0, failedCalls: 0 });
  const latestCall = calls[calls.length - 1];
  const terminalCalls = calls.filter((call) => call.info.status !== 'running' && call.info.status !== 'waiting_retry');
  const result = executorResultFor(state, entity, executorName, slug, calls);
  const projectedEntity = ['failed', 'unfulfillable', 'aborted', 'paused', 'waiting'].includes(result.status)
    ? { ...entity, status: result.status }
    : entity.status === 'running' && result.status === 'completed' && latestCall && latestCall.info.status !== 'running' && latestCall.info.status !== 'waiting_retry'
      ? { ...entity, status: latestCall.info.status === 'ok' ? 'completed' : 'failed' }
      : entity;
  const metrics = {
    ...baseMetrics,
    tokens: terminalCalls.reduce((total, call) => total + (call.info.tokensTotal ?? 0), 0) || baseMetrics.tokens,
    retries: terminalCalls.reduce((total, call) => total + call.retryEvents.length, 0) || undefined,
    calls: callMetrics.calls ?? baseMetrics.calls,
    successfulCalls: callMetrics.successfulCalls ?? baseMetrics.successfulCalls,
    failedCalls: callMetrics.failedCalls ?? baseMetrics.failedCalls,
  };
  const limits = executorLimitsFor(latestPayload(executorEvents, 'budget_snapshot') ?? latestPayload(executorEvents, 'limits_snapshot'));
  return {
    entity: projectedEntity,
    inspectorKey: entity.key,
    start,
    task,
    executorType,
    executorName,
    executorSlug: slug,
    kind: executorKindFor(slug),
    calls,
    result,
    info: executorInfoFor(result, calls, metrics.elapsedMs, limits),
    metrics,
    memoryResult: memoryComponentResult(executorEvents),
    memoryContext: memoryContextFor(executorEvents, calls),
    preflight: preflightFor(state, entity),
    prompt: promptFor(executorEvents, calls),
    access: accessFor(latestPayload(executorEvents, 'rbac_snapshot')?.rbac) ?? preflightFor(state, entity)?.access,
    limits,
    toolOverrides: toolOverridesFor(executorEvents),
  };
}

function synthesizerExecutorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  if (entity.type !== 'synthesis_run') return null;
  const start = startFor(state, entity);
  if (!start) return null;
  const calls = groupLogicalLlmCalls(entity.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((child): child is TraceEntity => Boolean(child))
    .map((child) => callFor(state, child))
    .filter((call): call is TraceCall => Boolean(call)));
  const limits = executorLimitsFor(latestPayload(eventsFor(state, entity), 'budget_snapshot'));
  const result = executorResultFor(state, entity, 'Синтезатор', 'synthesizer', calls);
  const baseMetrics = metricsFor(state, entity);
  const metrics = {
    ...baseMetrics,
    calls: calls.length || baseMetrics.calls,
    successfulCalls: calls.filter((call) => call.response && llmResponseStatus(call.response.payload) !== 'error').length || baseMetrics.successfulCalls,
    failedCalls: calls.filter((call) => call.response && llmResponseStatus(call.response.payload) === 'error').length || baseMetrics.failedCalls,
    tokens: calls.reduce((total, call) => total + (call.info.tokensTotal ?? 0), 0) || baseMetrics.tokens,
    retries: calls.reduce((total, call) => total + (call.retryEvents?.length ?? 0), 0) || baseMetrics.retries,
  };
  const executor: TraceExecutorRun = {
    entity,
    inspectorKey: `executor:${entity.key}`,
    start,
    task: 'Подготовка финального ответа',
    executorType: 'SYNTHESIZER',
    executorName: 'Синтезатор',
    executorSlug: 'synthesizer',
    kind: 'synthesizer',
    calls,
    result,
    info: executorInfoFor(result, calls, metrics.elapsedMs, limits),
    metrics,
    memoryContext: memoryContextFor(eventsFor(state, entity), calls),
    prompt: promptFor(eventsFor(state, entity), calls),
    limits,
  };
  executor.taskPresentation = taskPresentationForExecutor(state, executor);
  return executor;
}

function planForStage(state: SandboxTraceState, iteration: TraceEntity): PlanViewModel | undefined {
  const events = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .filter((event): event is RuntimeJournalEvent => Boolean(event));
  const planEvent = [...events].reverse().find((event) => (
    event.event_type === 'plan_iteration_applied'
    && (
      (asString(event.parent_entity_type ?? event.payload.parent_entity_type) === 'planner_iteration'
        && asString(event.parent_entity_id ?? event.payload.parent_entity_id) === iteration.id)
      || asString(event.payload.iteration_id) === iteration.id
    )
  ));
  if (planEvent) return projectPlan(planEvent.payload);
  const plannerResponse = [...events].reverse().find((event) => (
    event.event_type === 'llm_response'
    && event.payload.purpose === 'planning_decision'
    && asString(event.parent_entity_type ?? event.payload.parent_entity_type) === 'planner_iteration'
    && asString(event.parent_entity_id ?? event.payload.parent_entity_id) === iteration.id
  ));
  return plannerResponse ? projectPlan(llmResponseContent(plannerResponse.payload)) : undefined;
}

function failureForIteration(state: SandboxTraceState, iteration: TraceEntity): TraceStageFailure | undefined {
  if (resultStatusOf(iteration.status) !== 'failed') return undefined;
  const orchestratorKey = iteration.parentKey;
  if (!orchestratorKey) return undefined;
  const appliedPlanIds = new Set(state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .filter((event): event is RuntimeJournalEvent => Boolean(event) && event.event_type === 'plan_iteration_applied')
    .filter((event) => {
      const appliedIterationId = asString(event.parent_entity_id ?? event.payload.parent_entity_id)
        || asString(event.payload.iteration_id);
      const appliedIteration = appliedIterationId
        ? state.entitiesByKey[`planner_iteration:${appliedIterationId}`]
        : undefined;
      return appliedIteration?.parentKey === orchestratorKey;
    })
    .map((event) => asString(event.payload.plan_id) || asString(event.entity_id ?? event.payload.entity_id))
    .filter(Boolean));
  if (!appliedPlanIds.size) return undefined;
  const failedPlan = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .reverse()
    .find((event) => event.event_type === 'plan_failed'
      && appliedPlanIds.has(asString(event.entity_id ?? event.payload.entity_id)));
  if (!failedPlan) return undefined;
  const code = asString(failedPlan.payload.error_code) || undefined;
  const codeLabels: Record<string, string> = {
    planner_checkpoint_failed: 'Не удалось завершить перепланирование',
    planner_failed: 'Планировщик завершился с ошибкой',
  };
  const relatedError = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .find((event) => event.event_type === 'error'
      && (event.parent_entity_id === failedPlan.entity_id
        || asString(event.payload.plan_id) === asString(failedPlan.entity_id)));
  return {
    label: code ? codeLabels[code] ?? 'Этап завершился с ошибкой' : 'Этап завершился с ошибкой',
    code,
    message: resultMessageFrom(asRecord(relatedError?.payload) ?? {}) || undefined,
  };
}

function plannerExecutorFor(state: SandboxTraceState, iteration: TraceEntity): TraceExecutorRun | null {
  const start = startFor(state, iteration);
  if (!start) return null;
  const orchestrator = iteration.parentKey ? state.entitiesByKey[iteration.parentKey] : undefined;
  const orchestratorSnapshot = asRecord(orchestrator && startFor(state, orchestrator)?.payload.context_snapshot);
  const calls = groupLogicalLlmCalls(iteration.childKeys
    .map((key) => state.entitiesByKey[key])
    .filter((child): child is TraceEntity => Boolean(child))
    .map((child) => callFor(state, child))
    .filter((call): call is TraceCall => Boolean(call)));
  if (calls.length === 0) return null;
  // A planner iteration stays open while its planned tasks execute. The
  // planner executor itself is nevertheless done once its decision call has
  // completed; do not use the iteration container status for this card.
  const lastCall = calls[calls.length - 1];
  const planApplied = state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .some((event) => event?.event_type === 'plan_iteration_applied'
      && asString(event.payload.iteration_id) === iteration.id);
  const plannerEntity = (planApplied || lastCall?.info.status === 'ok')
    ? { ...iteration, status: 'completed' }
    : iteration;
  const result = executorResultFor(state, plannerEntity, 'Планер', 'planner', calls);
  const plannerCalls = calls.flatMap((call) => call.attempts ?? [call]);
  const plannerMetrics = metricsFor(state, plannerEntity);
  const metrics: TraceMetrics = {
    ...plannerMetrics,
    elapsedMs: plannerCalls.reduce((total, call) => total + (call.info.durationMs ?? 0), 0) || plannerMetrics.elapsedMs,
    tokens: plannerCalls.reduce((total, call) => total + (call.info.tokensTotal ?? 0), 0) || plannerMetrics.tokens,
    retries: plannerCalls.reduce((total, call) => total + call.retryEvents.length, 0) || undefined,
    calls: plannerCalls.length || plannerMetrics.calls,
    successfulCalls: plannerCalls.filter((call) => call.info.status === 'ok').length || undefined,
    failedCalls: plannerCalls.filter((call) => call.info.status === 'error').length || undefined,
  };
  return {
    entity: plannerEntity,
    inspectorKey: `executor:planner:${iteration.key}`,
    start,
    task: 'Принятие решения по плану',
    input: sanitizeDisplay(asRecord(orchestratorSnapshot?.inputs)),
    executorType: 'PLANNER',
    executorName: 'Планер',
    executorSlug: 'planner',
    kind: 'planner',
    calls,
    result,
    info: executorInfoFor(result, calls, metrics.elapsedMs),
    metrics,
    memoryContext: memoryContextFor(eventsFor(state, iteration), calls),
    prompt: promptFor(eventsFor(state, iteration), calls),
    access: accessFor(latestPayload(eventsFor(state, iteration), 'rbac_snapshot')?.rbac)
      ?? accessFor(orchestratorSnapshot?.rbac),
  };
}

function plannedTaskExecutorFor(
  state: SandboxTraceState,
  taskEntity: TraceEntity,
  plan: PlanViewModel | undefined,
): TraceExecutorRun | null {
  const start = eventsFor(state, taskEntity).find((event) => event.event_type === 'task_planned');
  if (!start) return null;
  const payload = start.payload;
  const taskId = asString(payload.task_id) || taskEntity.id;
  const planned = plan?.tasks.find((task) => task.taskId === taskId);
  const status = resultStatusOf(taskEntity.status);
  const result: TraceExecutorResult = {
    name: asString(payload.executor) || planned?.executor || 'Агент',
    status,
    statusLabel: traceResultStatusLabel(status),
    operations: { total: 0, succeeded: 0, failed: 0 },
  };
  const executor: TraceExecutorRun = {
    entity: taskEntity,
    inspectorKey: `executor:planned:${taskEntity.key}`,
    start,
    task: planned?.title || asString(payload.intent) || asString(payload.instructions) || taskId,
    executorType: 'AGENT',
    executorName: asString(payload.executor) || planned?.executor || 'Агент',
    executorSlug: asString(payload.executor) || planned?.executor || 'unknown',
    kind: 'agent',
    calls: [],
    result,
    info: executorInfoFor(result, [], undefined),
    metrics: metricsFor(state, taskEntity),
  };
  executor.taskPresentation = planned ?? projectPlanTask(payload, taskId);
  return executor;
}

function checkpointExecutorFor(state: SandboxTraceState, checkpoint: TraceEntity): TraceExecutorRun | null {
  const checkpointEvents = eventsFor(state, checkpoint);
  const start = checkpointEvents.find((event) => event.event_type === 'checkpoint_planned');
  if (!start) return null;
  const decisionEvent = [...checkpointEvents].reverse().find((event) => event.event_type === 'checkpoint_decided');
  const latest = decisionEvent?.payload ?? start.payload;
  const declaredNext = asString(latest.declared_next) || asString(start.payload.declared_next) || undefined;
  const effectiveNext = asString(latest.effective_next) || undefined;
  const next = effectiveNext || declaredNext;
  const reason = asString(latest.reason) || undefined;
  const reasonLabel = reason === 'task_failure' ? 'Предыдущая задача завершилась ошибкой'
    : reason === 'all_tasks_completed' ? 'Все запланированные задачи завершены'
      : reason === 'planner_terminal' ? 'Планировщик завершил план'
        : reason;
  const status = resultStatusOf(checkpoint.status);
  const result: TraceExecutorResult = {
    name: 'Контрольная точка',
    status,
    statusLabel: traceResultStatusLabel(status),
    output: reasonLabel,
    operations: { total: 0, succeeded: 0, failed: 0 },
  };
  const destination = next === 'synthesis' ? 'Синтез ответа'
    : next === 'planner' ? 'Повторное планирование'
      : next || 'не определён';
  const task = decisionEvent ? `Решение: ${destination}` : `Ожидание решения (планировщик предложил: ${destination})`;
  const executor: TraceExecutorRun = {
    entity: checkpoint,
    inspectorKey: `executor:checkpoint:${checkpoint.key}`,
    start,
    task,
    executorType: 'CHECKPOINT',
    executorName: 'Контрольная точка',
    executorSlug: 'checkpoint',
    kind: 'agent',
    calls: [],
    result,
    info: executorInfoFor(result, [], undefined),
    metrics: metricsFor(state, checkpoint),
  };
  executor.checkpoint = {
    declaredNext,
    effectiveNext,
    reason,
    iterationId: asString(latest.iteration_id) || asString(start.payload.iteration_id) || undefined,
    decided: Boolean(decisionEvent),
  };
  executor.taskPresentation = projectPlanTask({
    task_id: `checkpoint-${checkpoint.id}`,
    title: 'Контрольная точка',
    objective: task,
    status: checkpoint.status,
  });
  return executor;
}

function taskPresentationForExecutor(state: SandboxTraceState, executor: TraceExecutorRun, plan?: PlanViewModel): PlanTaskViewModel {
  const payload = executor.start.payload;
  const contextEvent = [...eventsFor(state, executor.entity)].reverse().find(
    event => event.event_type === 'status' && event.payload.stage === 'agent_context_snapshot',
  );
  const snapshot = asRecord(contextEvent?.payload.context_snapshot);
  const taskContext = asRecord(snapshot?.inputs);
  const taskId = asString(payload.task_id) || asString(taskContext?.task_id);
  const inputs = payload.task_inputs ?? taskContext?.inputs ?? taskContext?.dependency_outputs;
  const instructions = asString(payload.instructions) || asString(taskContext?.instructions);
  const intent = asString(payload.intent) || asString(taskContext?.intent);
  const planned = taskId ? plan?.tasks.find((task) => task.taskId === taskId) : undefined;
  if (planned) {
    return {
      ...planned,
      title: executor.task || planned.title,
      objective: asString(payload.task_objective) || planned.objective || asString(taskContext?.goal),
      executor: planned.executor ?? executor.executorSlug,
      status: planned.status ?? taskStatusLabel(executor.entity.status),
      inputs: inputs ?? planned.inputs,
      instructions: instructions || planned.instructions,
      intent: intent || planned.intent,
    };
  }
  return projectPlanTask({
    task_id: taskId || undefined,
    title: executor.task,
    objective: payload.task_objective ?? taskContext?.goal,
    instructions,
    intent,
    inputs,
    executor: executor.executorSlug,
    status: taskStatusLabel(executor.entity.status),
  }, taskId || executor.entity.id);
}

function taskPresentationForStep(
  payload: Record<string, unknown>,
  title: string,
  objective: string | undefined,
  executor: TraceExecutorRun | undefined,
  plan?: PlanViewModel,
): PlanTaskViewModel {
  const taskId = asString(payload.task_id) || asString(payload.phase_id);
  const planned = taskId ? plan?.tasks.find((task) => task.taskId === taskId) : undefined;
  if (planned) {
    return {
      ...planned,
      title: title || planned.title,
      objective: objective ?? planned.objective,
      executor: planned.executor ?? executor?.executorSlug,
      status: planned.status ?? taskStatusLabel(executor?.entity.status),
      inputs: payload.inputs ?? payload.task_inputs ?? executor?.taskPresentation?.inputs ?? planned.inputs,
    };
  }
  return projectPlanTask({
    task_id: taskId || undefined,
    title,
    objective,
    inputs: payload.inputs ?? payload.task_inputs ?? executor?.taskPresentation?.inputs,
    instructions: executor?.taskPresentation?.instructions,
    intent: executor?.taskPresentation?.intent,
    executor: executor?.executorSlug,
    status: taskStatusLabel(executor?.entity.status),
  }, taskId || executor?.entity.id || 'step-task');
}

function routePolicyFor(state: SandboxTraceState, entity: TraceEntity): TraceRoutePolicy | undefined {
  const events = eventsFor(state, entity);
  const decision = [...events].reverse().find((event) => event.event_type === 'route_policy_decision')?.payload;
  if (!decision) return undefined;
  const start = events.find((event) => event.event_type === 'route_policy_start')?.payload;
  const status = asString(decision.status);
  return {
    route: asString(decision.route) || undefined,
    status: status === 'matched' || status === 'unmatched' ? status : undefined,
    recommendationId: asString(decision.recommendation_id) || undefined,
    routeHint: asString(decision.route_hint) || undefined,
    matched: typeof decision.matched === 'boolean' ? decision.matched : undefined,
    ruleId: asString(decision.rule_id) || undefined,
    reasonCode: asString(decision.reason_code) || undefined,
    summary: asString(decision.summary) || undefined,
    detail: asString(decision.detail) || undefined,
    signals: stringArray(decision.signals),
    sourceAgent: asString(decision.source_agent) || undefined,
    userRequest: asString(start?.user_request) || undefined,
  };
}

function routePolicyExecutorFor(state: SandboxTraceState, entity: TraceEntity): TraceExecutorRun | null {
  const start = startFor(state, entity);
  if (!start) return null;
  const routePolicy = routePolicyFor(state, entity);
  if (!routePolicy) return null;
  const status = resultStatusOf(entity.status);
  const result: TraceExecutorResult = {
    name: 'Политика маршрутизации', status, statusLabel: traceResultStatusLabel(status),
    output: routePolicy.routeHint ?? routePolicy.route ?? routePolicy.status,
    message: routePolicy.summary ?? routePolicy.detail,
    operations: { total: 0, succeeded: 0, failed: 0 },
  };
  const metrics = metricsFor(state, entity);
  return {
    entity, inspectorKey: `executor:route-policy:${entity.key}`, start,
    task: 'Рекомендация для предварительной маршрутизации', executorType: 'POLICY',
    executorName: 'Рекомендация маршрута', executorSlug: 'root_route_policy', kind: 'route_policy',
    calls: [], result, info: executorInfoFor(result, [], metrics.elapsedMs), metrics, routePolicy,
  };
}

export function projectTraceStages(state: SandboxTraceState): TraceStage[] {
  const plannerStages = Object.values(state.entitiesByKey)
    .filter((entity) => entity.type === 'planner_iteration')
    .map((entity): TraceStage | null => {
      const start = startFor(state, entity);
      if (!start) return null;
      const number = asNumber(start.payload.iteration_number) ?? asNumber(start.payload.iteration) ?? 0;
      const directChildren = entity.childKeys
        .map((key) => state.entitiesByKey[key])
        .filter((child): child is TraceEntity => Boolean(child));
      const stepEntities = directChildren
        .filter((child) => child.type === 'step')
        .sort((left, right) => (startFor(state, left)?.sequence ?? 0) - (startFor(state, right)?.sequence ?? 0));
      const plannedTaskEntities = directChildren
        .filter((child) => child.type === 'task')
        .sort((left, right) => (eventsFor(state, left)[0]?.sequence ?? 0) - (eventsFor(state, right)[0]?.sequence ?? 0));
      const checkpointEntity = directChildren.find((child) => child.type === 'checkpoint');
      const executorRunsByStep = stepEntities.map((stepEntity) => (
        stepEntity.childKeys
          .map((key) => state.entitiesByKey[key])
          .filter((child): child is TraceEntity => Boolean(child))
          .map((child) => executorFor(state, child))
          .filter((executor): executor is TraceExecutorRun => Boolean(executor))
      ));
      const plannerExecutor = plannerExecutorFor(state, entity);
      const plan = planForStage(state, entity);
      const plannedTaskSteps = plannedTaskEntities.map((taskEntity) => {
        const relatedSteps = stepEntities.filter((stepEntity) => (
          eventsFor(state, stepEntity).some((event) => asString(event.payload.task_entity_id) === taskEntity.id)
        ));
        const attempts = new Map<string, TraceTaskAttempt>();
        relatedSteps.forEach((stepEntity) => {
          const index = stepEntities.indexOf(stepEntity);
          const stepEvents = eventsFor(state, stepEntity);
          const attemptId = stepEvents.map((event) => asString(event.payload.attempt_id)).find(Boolean) || `step:${stepEntity.id}`;
          const attempt = attempts.get(attemptId) ?? { id: attemptId, steps: [] };
          attempt.steps.push({ entity: stepEntity, executorRuns: executorRunsByStep[index] ?? [] });
          attempts.set(attemptId, attempt);
        });
        return {
          taskEntity,
          relatedSteps,
          attempts: [...attempts.values()],
          executors: relatedSteps.flatMap((stepEntity) => executorRunsByStep[stepEntities.indexOf(stepEntity)] ?? []),
        };
      });
      const plannedTaskExecutors = plannedTaskSteps
        .flatMap(({ taskEntity, executors }) => executors.length ? executors : [plannedTaskExecutorFor(state, taskEntity, plan)])
        .filter((executor): executor is TraceExecutorRun => Boolean(executor));
      const checkpointExecutor = checkpointEntity ? checkpointExecutorFor(state, checkpointEntity) : null;
      const executorRuns = [plannerExecutor, ...plannedTaskExecutors, checkpointExecutor, ...executorRunsByStep.flat()]
        .filter((executor): executor is TraceExecutorRun => Boolean(executor))
        .filter((executor, index, all) => all.findIndex((candidate) => candidate.inspectorKey === executor.inspectorKey) === index);
      const iterationType = asString(start.payload.iteration_type)
        || (executorRuns.some((executor) => executor.executorSlug === 'planner') ? 'decision' : 'execution');
      const task = iterationType === 'replan'
        ? 'Корректировка плана'
        : iterationType === 'checkpoint'
          ? 'Определение следующих шагов'
        : executorRuns.map((executor) => executor.task).find(Boolean)
        || asString(start.payload.task_title)
        || asString(start.payload.goal)
        || 'Выполнение задачи';
      for (const executor of executorRuns) executor.taskPresentation = taskPresentationForExecutor(state, executor, plan);
      const stage: TraceStage = {
        entity,
        start,
        number,
        iterationNumber: number,
        stepNumber: 0,
        iterationType,
        kind: 'iteration',
        label: iterationLabel(iterationType, number),
        task,
        plan,
        steps: [],
        executorRuns,
        metrics: aggregateMetrics(metricsFor(state, entity), executorRuns.map((executor) => executor.metrics)),
        failure: failureForIteration(state, entity),
      };
      const plannerSteps: TraceStep[] = plannerExecutor ? [{
        key: `${entity.key}:planner-decision`,
        entity,
        stage,
        number: 1,
        kind: 'planner_decision',
        title: 'Принятие решения по плану',
        taskPresentation: projectPlanTask({
          task_id: `planner-${number}`,
          title: 'Принятие решения по плану',
          executor: 'planner',
          status: taskStatusLabel(plannerExecutor.entity.status),
        }),
        executorRuns: [plannerExecutor],
        metrics: plannerExecutor.metrics,
      }] : [];
      const taskSteps: TraceStep[] = plannedTaskSteps.map(({ taskEntity, relatedSteps, attempts, executors }, index) => {
        const stepEntity = relatedSteps[0];
        const stepStart = stepEntity ? startFor(state, stepEntity) : undefined;
        const payload = stepStart?.payload ?? eventsFor(state, taskEntity)[0]?.payload ?? {};
        const executor = executors[0] ?? plannedTaskExecutorFor(state, taskEntity, plan);
        const planned = plan?.tasks.find((task) => task.taskId === asString(payload.task_id));
        const title = planned?.title || asString(payload.intent) || asString(payload.title) || executor?.task || 'Запланированная задача';
        const objective = planned?.objective || asString(payload.instructions) || asString(payload.objective) || undefined;
        return {
          key: taskEntity.key,
          entity: taskEntity,
          stage,
          number: index + 1 + plannerSteps.length,
          kind: 'task_execution',
          taskId: asString(payload.task_id) || undefined,
          title,
          objective,
          inputs: payload.inputs,
          taskPresentation: planned ?? taskPresentationForStep(payload, title, objective, executor, plan),
          executorRuns: executors.length ? executors : executor ? [executor] : [],
          attempts,
          metrics: aggregateMetrics(metricsFor(state, taskEntity), [
            ...relatedSteps.map((step) => metricsFor(state, step)),
            ...executors.map((item) => item.metrics),
          ]),
        };
      });
      const unplannedSteps = stepEntities
        .filter((stepEntity) => !plannedTaskSteps.some((item) => item.relatedSteps.some((related) => related.key === stepEntity.key)))
        .map((stepEntity, index) => {
        const stepStart = startFor(state, stepEntity);
        const payload = stepStart?.payload ?? {};
        const stepExecutors = executorRunsByStep[stepEntities.indexOf(stepEntity)];
        const executor = stepExecutors[0];
        const title = asString(payload.title) || asString(payload.task_title) || asString(payload.task_objective) || executor?.task || stage.task;
        const objective = asString(payload.objective) || asString(payload.task_objective) || undefined;
        return {
          key: stepEntity.key,
          entity: stepEntity,
          stage,
          number: asNumber(payload.step_number) ?? index + 1 + plannerSteps.length + taskSteps.length,
          kind: stepKindFor(stage.kind, executor),
          taskId: asString(payload.task_id) || asString(payload.phase_id) || undefined,
          title,
          objective,
          inputs: payload.inputs ?? payload.task_inputs,
          taskPresentation: taskPresentationForStep(payload, title, objective, executor, plan),
          executorRuns: stepExecutors,
          metrics: aggregateMetrics(metricsFor(state, stepEntity), stepExecutors.map((executor) => executor.metrics)),
        };
      });
      const checkpointSteps: TraceStep[] = checkpointExecutor && checkpointEntity ? [{
        key: checkpointEntity.key,
        entity: checkpointEntity,
        stage,
        number: plannerSteps.length + taskSteps.length + unplannedSteps.length + 1,
        kind: 'task_execution',
        title: 'Контрольная точка',
        objective: checkpointExecutor.task,
        taskPresentation: checkpointExecutor.taskPresentation!,
        executorRuns: [checkpointExecutor],
        metrics: checkpointExecutor.metrics,
      }] : [];
      stage.steps = [...plannerSteps, ...taskSteps, ...unplannedSteps, ...checkpointSteps];
      stage.stepNumber = stage.steps[0]?.number ?? 0;
      return stage;
    })
    .filter((stage): stage is TraceStage => stage !== null)
    .sort((left, right) => left.start.sequence - right.start.sequence);
  const systemStages = Object.values(state.entitiesByKey)
    .filter((entity) => entity.type === 'orchestrator' || entity.type === 'synthesis_run' || entity.type === 'route_policy')
    .map((entity): TraceStage | null => {
      const start = startFor(state, entity);
      if (!start) return null;
      const isRoutePolicy = entity.type === 'route_policy';
      const isPreflight = entity.type === 'orchestrator' && asString(start.payload.role) === 'turn_preflight';
      const isMemory = entity.type === 'orchestrator' && asString(start.payload.role) === 'memory';
      const isMemoryPreparation = entity.type === 'orchestrator' && ['memory_preparation', 'memory_recall'].includes(asString(start.payload.role));
      const isSynthesis = entity.type === 'synthesis_run';
      const memoryStage = asString(start.payload.memory_stage);
      if (!isRoutePolicy && !isPreflight && !isMemory && !isMemoryPreparation && !isSynthesis) return null;
      const executorRuns = isRoutePolicy
        ? [routePolicyExecutorFor(state, entity)].filter((executor): executor is TraceExecutorRun => Boolean(executor))
        : isSynthesis
        ? [synthesizerExecutorFor(state, entity)].filter((executor): executor is TraceExecutorRun => Boolean(executor))
        : isPreflight
          ? (() => {
              const preflightChildren = [
                ...entity.childKeys.map((key) => state.entitiesByKey[key]),
                ...Object.values(state.entitiesByKey).filter((child) => (
                  child.type === 'llm_call'
                  && child.parentKey === `turn_preflight:${entity.id}`
                )),
              ];
              const calls = groupLogicalLlmCalls(preflightChildren
                .filter((child): child is TraceEntity => Boolean(child))
                .map((child) => callFor(state, child))
                .filter((call): call is TraceCall => Boolean(call)));
              const result = executorResultFor(state, entity, 'Turn Preflight', 'turn_preflight', calls);
              const metrics = metricsFor(state, entity);
              return [{
                entity, inspectorKey: `executor:preflight:${entity.key}`, start,
                task: 'Разбор запроса и выбор маршрута', executorType: 'ОРКЕСТРАТОР', executorName: 'Предварительная маршрутизация',
                executorSlug: 'turn_preflight', kind: 'preflight', calls, result, route: routeFor(calls, eventsFor(state, entity)),
                info: executorInfoFor(result, calls, metrics.elapsedMs), metrics,
                memoryContext: memoryContextFor(eventsFor(state, entity), calls),
                prompt: promptFor(eventsFor(state, entity), calls),
              } satisfies TraceExecutorRun];
            })()
        : entity.childKeys
          .map((key) => state.entitiesByKey[key])
          .filter((child): child is TraceEntity => Boolean(child))
          .map((child) => executorFor(state, child))
          .filter((executor): executor is TraceExecutorRun => Boolean(executor));
      const stage: TraceStage = {
        entity, start, number: plannerStages.length + 1, iterationNumber: plannerStages.length + 1,
        stepNumber: 0, iterationType: isRoutePolicy ? 'route_policy' : isSynthesis ? 'synthesis' : isPreflight ? 'turn_preflight' : 'memory',
        kind: isRoutePolicy ? 'route_policy' : isSynthesis ? 'synthesis' : isPreflight ? 'turn_preflight' : isMemoryPreparation ? 'memory_preparation' : 'memory_writeback',
        label: isRoutePolicy ? 'Рекомендация маршрута' : memoryStage === 'screening' ? 'Скрининг документа'
          : memoryStage === 'study_sections' ? 'Извлечение из секций'
            : memoryStage === 'finalize_review' ? 'Финализация и проверка конфликтов'
              : memoryStage === 'reconcile_conflicts' ? 'Повторная проверка конфликтов'
                : isSynthesis ? 'Подготовка ответа' : isPreflight ? 'Предварительная маршрутизация' : isMemoryPreparation ? 'Подготовка контекста' : 'Сохранение контекста диалога',
        task: memoryStage === 'screening' ? 'Определение полезности документа для памяти'
          : memoryStage === 'study_sections' ? 'Извлечение кандидатов из секций документа'
            : memoryStage === 'finalize_review' ? 'Подготовка кандидатов к админской проверке'
              : memoryStage === 'reconcile_conflicts' ? 'Повторная проверка конфликтов памяти'
                : isRoutePolicy ? 'Сигналы для TurnPreflight' : isSynthesis ? 'Подготовка финального ответа' : isPreflight ? 'Разбор запроса и выбор маршрута' : isMemoryPreparation ? 'Отбор контекста для планера' : 'Сохранение фактов и сводки', steps: [], executorRuns,
        metrics: aggregateMetrics(metricsFor(state, entity), executorRuns.map((executor) => executor.metrics)),
        routePolicy: isRoutePolicy ? routePolicyFor(state, entity) : undefined,
      };
      if (isMemory || isMemoryPreparation) {
        stage.steps = executorRuns.map((executor, index) => ({
          key: `${entity.key}:memory-step:${executor.entity.id}`,
          entity: executor.entity,
          stage,
          number: index + 1,
          kind: stepKindFor(stage.kind, executor),
          title: memoryStage === 'screening' ? 'Скрининг документа'
            : memoryStage === 'study_sections' ? 'Извлечение кандидатов'
              : memoryStage === 'finalize_review' ? 'Финализация и конфликты'
                : memoryStage === 'reconcile_conflicts' ? 'Проверка конфликтов'
            : executor.executorSlug === 'fact_extractor' ? 'Извлечение фактов'
            : executor.executorSlug === 'fact_compactor' ? 'Компактация фактов'
              : 'Подготовка memory context',
          objective: executor.task,
          taskPresentation: taskPresentationForExecutor(state, executor),
          executorRuns: [executor],
          metrics: executor.metrics,
        }));
        stage.stepNumber = stage.steps[0]?.number ?? 0;
      }
      return stage;
    })
    .filter((stage): stage is TraceStage => stage !== null);
  return [...plannerStages, ...systemStages].sort((left, right) => left.start.sequence - right.start.sequence);
}

function runEvents(state: SandboxTraceState): RuntimeJournalEvent[] {
  return state.eventIdsBySequence
    .map((id) => state.eventsById[id])
    .filter((event): event is RuntimeJournalEvent => Boolean(event));
}

function attachmentList(value: unknown): TraceAttachment[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap((item): TraceAttachment[] => {
    const record = asRecord(item);
    const artifactId = asString(record?.artifact_id);
    const fileName = asString(record?.file_name);
    if (!artifactId || !fileName || seen.has(artifactId)) return [];
    seen.add(artifactId);
    return [{
      artifactId,
      fileName,
      downloadUrl: asString(record?.download_url) || undefined,
      contentType: asString(record?.content_type) || undefined,
      sizeBytes: asNumber(record?.size_bytes),
    }];
  });
}

function safeRunError(events: RuntimeJournalEvent[]): string | undefined {
  const terminalFailure = [...events].reverse().find((event) => event.event_type === 'run_end' || event.event_type === 'run_failed');
  const failedRun = terminalFailure?.event_type === 'run_failed'
    || ['failed', 'error'].includes(asString(terminalFailure?.payload.status).toLowerCase());
  for (const event of [...events].reverse()) {
    if (event.event_type !== 'error' && event.event_type !== 'run_failed') continue;
    const payload = event.payload;
    if (!failedRun && (payload.recoverable === true || payload.retryable === true)) continue;
    const message = asString(payload.safe_message) || asString(payload.user_message) || asString(payload.message) || asString(payload.error);
    if (message) return message;
  }
  return undefined;
}

export function projectTraceRun(state: SandboxTraceState): TraceRunView {
  const events = runEvents(state);
  const runTerminal = [...events].reverse().find((event) => event.event_type === 'run_end' || event.event_type === 'run_failed');
  const runStatus = asString(runTerminal?.payload.status).toLowerCase();
  // One journal fact is the accepted answer. SSE `final`, deltas and executor
  // outputs are transport/intermediate data and cannot backfill run history.
  const answerMarker = [...events].reverse().find((event) => (
    event.event_type === 'final_answer_marker'
    && event.entity_type === 'run'
    && event.entity_id === state.runId
    && event.parent_entity_type === 'synthesis_run'
    && event.payload.status === 'completed'
  ));
  // A completed synthesis result remains useful even when a later run-level
  // terminal event reports partial failure (for example, the planner failed
  // after a prior task produced enough material). Keep run status/error as a
  // separate fact instead of erasing the accepted answer.
  const finalContent = asString(answerMarker?.payload.content);
  const attachments = attachmentList(answerMarker?.payload.attachments);
  const sources = answerMarker?.payload.sources;
  const lastWaiting = [...events].reverse().find((event) => event.event_type === 'waiting_input' || event.event_type === 'confirmation_required');
  const lastAnswer = [...events].reverse().find((event) => event.event_type === 'question_answer');
  const waiting = lastWaiting && (!lastAnswer || lastWaiting.sequence > lastAnswer.sequence) ? lastWaiting : undefined;
  const waitingPayload = waiting?.payload;
  const pause = waiting ? {
    kind: waiting.event_type === 'confirmation_required' ? 'confirmation' as const : 'input' as const,
    question: asString(waitingPayload?.question) || undefined,
    message: asString(waitingPayload?.message) || asString(waitingPayload?.summary) || undefined,
  } : undefined;
  const root = state.rootEntityKey ? state.entitiesByKey[state.rootEntityKey] : undefined;
  // Budgets are owned by the run. A nested executor snapshot is not a run budget.
  const budgetSnapshot = root
    ? [...eventsFor(state, root)].reverse().find((event) => event.event_type === 'budget_snapshot' || event.event_type === 'run_budget_snapshot')?.payload
    : undefined;
  const terminal = runTerminal;
  const status = asString(terminal?.payload.status)
    || (terminal?.event_type === 'run_failed' ? 'failed' : undefined)
    || (root?.status && root.status !== 'running' ? root.status : undefined)
    || (pause ? (pause.kind === 'input' ? 'waiting_input' : 'waiting_confirmation') : root?.status || 'unknown');
  return { runId: state.runId, status, finalContent, attachments, sources, error: safeRunError(events), pause, limits: limitsFor(budgetSnapshot) };
}

export function stepFor(stage: TraceStage): TraceStep {
  const firstStep = stage.steps[0];
  if (firstStep) return firstStep;
  const executor = stage.executorRuns[0];
  const payload = executor?.start.payload ?? stage.start.payload;
  const title = asString(payload.title) || asString(payload.task_title) || asString(payload.task_objective) || stage.task;
  const objective = asString(payload.objective) || asString(payload.task_objective) || undefined;
  return {
    key: `step:${stage.entity.key}`,
    entity: stage.entity,
    stage,
    number: stage.stepNumber,
    kind: stepKindFor(stage.kind, executor),
    taskId: asString(payload.task_id) || asString(payload.phase_id) || undefined,
    title,
    objective,
    inputs: payload.inputs ?? payload.task_inputs,
    taskPresentation: taskPresentationForStep(payload, title, objective, executor, stage.plan),
    executorRuns: stage.executorRuns,
    metrics: stage.metrics,
  };
}

/** Resolve a stable inspector selection against the latest normalized trace. */
export function resolveTraceInspectionTarget(
  state: SandboxTraceState,
  key: string,
): TraceInspectionTarget | null {
  for (const stage of projectTraceStages(state)) {
    for (const step of stage.steps.length > 0 ? stage.steps : [stepFor(stage)]) {
      if (step.key === key) {
        const target: TraceInspectionTarget = { kind: 'step', key, step, tabs: [] };
        return withTraceInspectorTabs(target);
      }
    }
    for (const executor of stage.executorRuns) {
      if (executor.inspectorKey === key) {
        const target: TraceInspectionTarget = { kind: 'executor', key, executor, stage, tabs: [] };
        return withTraceInspectorTabs(target);
      }
      for (const call of executor.calls) {
        if (call.entity.key === key) {
          const target: TraceInspectionTarget = call.kind === 'error'
            ? { kind: 'error', key, call, executor, stage, tabs: [] }
            : { kind: 'call', key, call, executor, stage, tabs: [] };
          return withTraceInspectorTabs(target);
        }
      }
    }
    if (stage.entity.key === key) {
      const target: TraceInspectionTarget = { kind: 'stage', key, stage, tabs: [] };
      return withTraceInspectorTabs(target);
    }
  }
  return null;
}

export function traceElapsedMs(state: SandboxTraceState, now: number): number | undefined {
  const events = state.eventIdsBySequence.map((id) => state.eventsById[id]).filter(Boolean);
  if (events.length === 0) return undefined;
  const start = new Date(events[0].occurred_at).getTime();
  let terminal = [...events].reverse().find((event) => event.event_type === 'run_end');
  // Agent-run endpoints return the closed agent subgraph without root run events.
  // A sandbox run continues after an agent ends, so only use this fallback when
  // the journal has no run_start and every observed agent execution has ended.
  if (!terminal && !events.some(event => event.event_type === 'run_start')) {
    const starts = events.filter(event => event.event_type === 'agent_start');
    const ends = events.filter(event => event.event_type === 'agent_end');
    if (starts.length && starts.every(startEvent => ends.some(endEvent => endEvent.entity_id === startEvent.entity_id))) {
      terminal = ends.at(-1);
    }
  }
  const finish = terminal ? new Date(terminal.occurred_at).getTime() : now;
  return finish > start ? finish - start : undefined;
}
