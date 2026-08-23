import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceCall } from '../../traceProjection';
import { callDisplayName, formatFieldLabel, llmMessages, llmResponseContent, parseCallContent, purposeLabel, toDisplayEntries, toolResult, type DisplayEntry, type ToolNameMap } from '../../callInspection';
import { callPresentation, callStatusPresentation, formatCallDuration } from '../../callPresentation';
import { ExecutionContextViewer } from './viewers/ExecutionContextViewer';
import { ExtractionResultViewer } from './viewers/ExtractionResultViewer';
import { PlanView } from './TraceDataViews';
import styles from './CallViews.module.css';

function Value({ value, structured = false }: { value: unknown; structured?: boolean }) {
  if (value === null || value === undefined || typeof value === 'boolean' || typeof value === 'number') return <InspectorScalar value={value as string | number | boolean | null | undefined} />;
  if (typeof value === 'string' && !structured) return value.includes('\n') || value.length > 120
    ? <InspectorTextBlock text={value} />
    : <InspectorScalar value={value} />;
  const parsed = structured ? parseCallContent(value) : { kind: 'json' as const, data: value };
  if (parsed.kind === 'text') return <InspectorTextBlock text={parsed.text ?? '—'} />;
  if (parsed.data === null || parsed.data === undefined || typeof parsed.data === 'boolean' || typeof parsed.data === 'number') return <InspectorScalar value={parsed.data as number | boolean | null | undefined} />;
  return <InspectorJsonBlock value={parsed.data ?? '—'} />;
}

function Fields({ entries }: { entries: DisplayEntry[] }) {
  const statusTone = (value: unknown): 'neutral' | 'success' | 'warn' | 'danger' | 'info' => {
    const normalized = String(value ?? '').toLowerCase();
    if (normalized.includes('ошиб')) return 'danger';
    if (normalized.includes('успеш') || normalized.includes('готов')) return 'success';
    if (normalized.includes('ожида')) return 'warn';
    return 'info';
  };
  return <InspectorFieldGroup>{entries.length ? entries.map((entry) => <InspectorFieldRow key={entry.label} label={entry.label}>{entry.label === 'Статус' ? <InspectorStatus label={String(entry.value ?? '—')} tone={statusTone(entry.value)} /> : <Value value={entry.value} />}</InspectorFieldRow>) : <InspectorFieldRow label="Данные">—</InspectorFieldRow>}</InspectorFieldGroup>;
}

export function LlmTokenUsage({ input, output, total }: { input?: number; output?: number; total?: number }) {
  const format = (value: number | undefined) => value === undefined ? '—' : new Intl.NumberFormat('ru-RU').format(value);
  return <div className={styles.tokenUsage} aria-label="Расход токенов">
    <span className={styles.tokensIn}>in {format(input)}</span>
    <span className={styles.tokensOut}>out {format(output)}</span>
    <span className={styles.tokensTotal}>all {format(total)}</span>
  </div>;
}

export function LlmInfoView({ call }: { call: TraceCall }) {
  const request = call.request.payload;
  const presentation = callPresentation(call);
  const status = callStatusPresentation(presentation.status);
  const model = request.model ?? call.response?.payload.model;
  const result = presentation.status !== 'error' ? presentation.outcome : undefined;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={status.label} tone={status.tone} /></InspectorFieldRow>
    <InspectorFieldRow label="Назначение"><InspectorScalar value={purposeLabel(request.purpose)} /></InspectorFieldRow>
    <InspectorFieldRow label="Модель"><InspectorScalar value={model as string | number | boolean | null | undefined} /></InspectorFieldRow>
    {result ? <InspectorFieldRow label="Результат"><InspectorStatus label={result.count ? `${result.label} · ${result.count}` : result.label} tone="info" /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Расход"><LlmTokenUsage input={presentation.tokensIn} output={presentation.tokensOut} total={presentation.tokensTotal} /></InspectorFieldRow>
    <InspectorFieldRow label="Длительность"><InspectorScalar value={formatCallDuration(presentation.durationMs)} /></InspectorFieldRow>
    <InspectorFieldRow label="Повторы"><InspectorStatus label={String(presentation.retryCount)} tone={presentation.retryCount > 0 ? 'warn' : 'neutral'} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function LlmErrorView({ call }: { call: TraceCall }) {
  const error = callPresentation(call).error;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label="Ошибка" tone="danger" /></InspectorFieldRow>
    <InspectorFieldRow label="Название ошибки"><InspectorScalar value={error?.name} /></InspectorFieldRow>
    {error?.code ? <InspectorFieldRow label="Код ошибки"><InspectorScalar value={error.code} /></InspectorFieldRow> : null}
    {error?.message ? <InspectorFieldRow label="Сообщение"><InspectorTextBlock text={error.message} /></InspectorFieldRow> : null}
    {error?.statusCode !== undefined ? <InspectorFieldRow label="HTTP-статус"><InspectorScalar value={error.statusCode} /></InspectorFieldRow> : null}
    {error?.providerCode ? <InspectorFieldRow label="Код провайдера"><InspectorScalar value={error.providerCode} /></InspectorFieldRow> : null}
    {error?.retryable !== undefined ? <InspectorFieldRow label="Можно повторить"><InspectorStatus label={error.retryable ? 'Да' : 'Нет'} tone={error.retryable ? 'warn' : 'neutral'} /></InspectorFieldRow> : null}
    {error?.retryAfterMs !== undefined ? <InspectorFieldRow label="Повтор через"><InspectorScalar value={formatCallDuration(error.retryAfterMs)} /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Повторы"><InspectorScalar value={callPresentation(call).retryCount} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function CallInfoView({ call }: { call: TraceCall }) {
  return <Fields entries={toDisplayEntries(call.request.payload)} />;
}

export function ToolInfoView({ call, toolNames, description }: { call: TraceCall; toolNames?: ToolNameMap; description?: string }) {
  const request = call.request.payload;
  const presentation = callPresentation(call);
  const status = callStatusPresentation(presentation.status);
  const task = String(request.description ?? request.intent ?? description ?? '—');
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={status.label} tone={status.tone} /></InspectorFieldRow>
    <InspectorFieldRow label="Название тулза"><InspectorScalar value={callDisplayName(String(request.tool ?? ''), toolNames)} /></InspectorFieldRow>
    <InspectorFieldRow label="Задача"><InspectorTextBlock text={task} /></InspectorFieldRow>
    <InspectorFieldRow label="Длительность"><InspectorScalar value={formatCallDuration(presentation.durationMs)} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function LlmRequestSnapshotView({ call, executionSnapshot }: { call: TraceCall; executionSnapshot?: unknown }) {
  const messages = llmMessages(call.request.payload);
  const request = call.request.payload;
  const roleLabel = (role: string): string => ({ system: 'Система', user: 'Пользователь', assistant: 'Ассистент', tool: 'Инструмент' }[role] ?? formatFieldLabel(role));
  return <div className={styles.messages}>
    <InspectorFieldGroup>
      {request.temperature !== undefined ? <InspectorFieldRow label="Температура"><InspectorScalar value={request.temperature as number} /></InspectorFieldRow> : null}
      {request.max_tokens !== undefined ? <InspectorFieldRow label="Лимит токенов"><InspectorScalar value={request.max_tokens as number} /></InspectorFieldRow> : null}
      {request.request_bytes !== undefined ? <InspectorFieldRow label="Размер запроса"><InspectorScalar value={`${request.request_bytes} B`} /></InspectorFieldRow> : null}
      {request.input_tokens_estimate !== undefined ? <InspectorFieldRow label="Оценка входных токенов"><InspectorScalar value={request.input_tokens_estimate as number} /></InspectorFieldRow> : null}
      {request.response_schema_bytes !== undefined ? <InspectorFieldRow label="Размер response schema"><InspectorScalar value={`${request.response_schema_bytes} B`} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    {messages.length ? messages.map((message, index) => <div key={`${message.role}:${index}`} className={`${styles.message} ${styles[message.role] ?? ''}`}><div className={styles.messageHeader}><span>{roleLabel(message.role)}</span>{message.role === 'system' ? <span>системный контекст</span> : null}</div><Value value={message.content.data ?? message.content.text} structured /></div>) : <Fields entries={toDisplayEntries(call.request.payload)} />}
    <ExecutionContextViewer snapshot={executionSnapshot} />
  </div>;
}

export function LlmResponseSnapshotView({ call, toolNames }: { call: TraceCall; toolNames?: ToolNameMap }) {
  const presentation = callPresentation(call);
  const payload = call.response?.payload;
  if (!payload) return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label="Ожидается" tone="warn" /></InspectorFieldRow></InspectorFieldGroup>;
  if (presentation.status === 'waiting_retry') return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label="Ожидает повтора" tone="warn" /></InspectorFieldRow>{presentation.error?.retryAfterMs !== undefined ? <InspectorFieldRow label="Повтор через"><InspectorScalar value={formatCallDuration(presentation.error.retryAfterMs)} /></InspectorFieldRow> : null}</InspectorFieldGroup>;
  if (presentation.status === 'error') return <InspectorFieldGroup><InspectorFieldRow label="Результат"><InspectorScalar value="Нет результата" /></InspectorFieldRow></InspectorFieldGroup>;
  const semanticOutcome = presentation.outcome;
  const parsed = parseCallContent(llmResponseContent(payload));
  const metadata = <InspectorFieldGroup>
    {payload.result_kind !== undefined ? <InspectorFieldRow label="Тип результата"><InspectorScalar value={String(payload.result_kind)} /></InspectorFieldRow> : null}
    {payload.response_length !== undefined ? <InspectorFieldRow label="Размер ответа"><InspectorScalar value={`${payload.response_length} B`} /></InspectorFieldRow> : null}
    {payload.terminal !== undefined ? <InspectorFieldRow label="Терминальный"><InspectorScalar value={payload.terminal === true ? 'Да' : 'Нет'} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
  if (semanticOutcome?.kind === 'tools') {
    if (parsed.kind === 'tool_call') {
      const toolCall = parsed.data as Record<string, unknown>;
      return <div className={styles.list}>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Выбранная операция">{callDisplayName(String(toolCall.tool ?? '—'), toolNames)}</InspectorFieldRow><InspectorFieldRow label="Аргументы"><Value value={toolCall.arguments ?? {}} /></InspectorFieldRow></InspectorFieldGroup></div>;
    }
    return <div className={styles.list}>{metadata}
      <InspectorFieldGroup><InspectorFieldRow label="Результат"><InspectorStatus label={semanticOutcome.count ? `${semanticOutcome.label} · ${semanticOutcome.count}` : semanticOutcome.label} tone="info" /></InspectorFieldRow></InspectorFieldGroup>
      {presentation.linkedToolCalls.map((toolCall, index) => <div key={toolCall.id} className={styles.listItem}>
        <div className={styles.listTitle}>{callDisplayName(String(toolCall.payload.tool ?? '—'), toolNames)}</div>
        <ToolRequest value={toolCall.payload.arguments} />
      </div>)}
    </div>;
  }
  if (semanticOutcome?.kind === 'plan') return <div className={styles.list}>{metadata}<PlanView plan={parsed.data} /></div>;
  if (parsed.kind === 'tool_call') {
    const toolCall = parsed.data as Record<string, unknown>;
    return <div className={styles.list}>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Выбранная операция">{callDisplayName(String(toolCall.tool ?? '—'), toolNames)}</InspectorFieldRow><InspectorFieldRow label="Аргументы"><Value value={toolCall.arguments ?? {}} /></InspectorFieldRow></InspectorFieldGroup></div>;
  }
  if (parsed.kind === 'json') return <div className={styles.list}>{metadata}<Fields entries={toDisplayEntries(parsed.data)} /></div>;
  return <div className={styles.list}>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Ответ"><Value value={parsed.text} /></InspectorFieldRow></InspectorFieldGroup></div>;
}

export const LlmRequestView = LlmRequestSnapshotView;
export const LlmResponseView = LlmResponseSnapshotView;

export function ToolRequest({ value }: { value: unknown }) {
  const object = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const entries = Object.entries(object);
  if (!entries.length) return <InspectorFieldGroup><InspectorFieldRow label="Запрос">Нет аргументов</InspectorFieldRow></InspectorFieldGroup>;
  return <InspectorFieldGroup>{entries.map(([key, item]) => (
    <InspectorFieldRow key={key} label={formatFieldLabel(key)}><Value value={item} /></InspectorFieldRow>
  ))}</InspectorFieldGroup>;
}

export function ToolRequestView({ call }: { call: TraceCall }) {
  return <ToolRequest value={call.request.payload.arguments} />;
}

export function ToolResponse({ call }: { call: TraceCall }) {
  const presentation = callPresentation(call);
  if (!call.response) return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label={presentation.status === 'waiting_retry' ? 'Ожидает повтора' : 'Ожидается'} tone="warn" /></InspectorFieldRow></InspectorFieldGroup>;
  const result = toolResult(call.response.payload);
  const isTruncated = call.response.payload.truncated === true;
  const items = Array.isArray(result.data) ? result.data : Array.isArray((result.data as Record<string, unknown>)?.templates) ? (result.data as Record<string, unknown>).templates as unknown[] : Array.isArray((result.data as Record<string, unknown>)?.hits) ? (result.data as Record<string, unknown>).hits as unknown[] : [];
  return <div className={styles.list}>
    <div className={`${styles.summary} ${presentation.status === 'error' ? styles.failure : styles.success}`}><Fields entries={result.details} />{result.message ? <InspectorTextBlock text={result.message} /> : null}</div>
    {typeof result.data === 'string' && result.data ? <InspectorFieldGroup><InspectorFieldRow label="Предпросмотр результата"><InspectorTextBlock text={result.data} /></InspectorFieldRow>{isTruncated ? <InspectorFieldRow label="Результат">Сокращён</InspectorFieldRow> : null}</InspectorFieldGroup> : null}
    {items.map((item, index) => { const entry = item as Record<string, unknown>; return <div key={index} className={styles.listItem}><div className={styles.listTitle}>{String(entry.title ?? entry.primary_fragment ?? entry.name ?? `Элемент ${index + 1}`)}</div><Fields entries={toDisplayEntries(entry.row_data ?? entry)} /></div>; })}
    {!items.length && result.data !== undefined && result.data !== null && typeof result.data !== 'string' ? <div className={styles.summary}><Fields entries={toDisplayEntries(result.data)} /></div> : null}
    <ExtractionResultViewer extraction={call.extraction} />
  </div>;
}

export const ToolResponseView = ToolResponse;
