import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceCall } from '../../traceProjection';
import { callDisplayName, formatFieldLabel, parseCallContent, type DisplayEntry, type ToolNameMap } from '../../callInspection';
import { callStatusPresentation, formatCallDuration } from '../../callPresentation';
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
  const request = call.requestView;
  const status = callStatusPresentation(call.info.status);
  const result = call.info.status !== 'error' ? call.info.outcome : undefined;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={status.label} tone={status.tone} /></InspectorFieldRow>
    <InspectorFieldRow label="Назначение"><InspectorScalar value={request.purpose} /></InspectorFieldRow>
    <InspectorFieldRow label="Модель"><InspectorScalar value={request.model} /></InspectorFieldRow>
    {result ? <InspectorFieldRow label="Результат"><InspectorStatus label={result.count ? `${result.label} · ${result.count}` : result.label} tone="info" /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Расход"><LlmTokenUsage input={call.info.tokensIn} output={call.info.tokensOut} total={call.info.tokensTotal} /></InspectorFieldRow>
    <InspectorFieldRow label="Длительность"><InspectorScalar value={formatCallDuration(call.info.durationMs)} /></InspectorFieldRow>
    <InspectorFieldRow label="Повторы"><InspectorStatus label={String(call.info.retryCount)} tone={call.info.retryCount > 0 ? 'warn' : 'neutral'} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function LlmErrorView({ call }: { call: TraceCall }) {
  const error = call.errorView;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label="Ошибка" tone="danger" /></InspectorFieldRow>
    <InspectorFieldRow label="Название ошибки"><InspectorScalar value={error?.name} /></InspectorFieldRow>
    {error?.code ? <InspectorFieldRow label="Код ошибки"><InspectorScalar value={error.code} /></InspectorFieldRow> : null}
    {error?.message ? <InspectorFieldRow label="Сообщение"><InspectorTextBlock text={error.message} /></InspectorFieldRow> : null}
    {error?.statusCode !== undefined ? <InspectorFieldRow label="HTTP-статус"><InspectorScalar value={error.statusCode} /></InspectorFieldRow> : null}
    {error?.providerCode ? <InspectorFieldRow label="Код провайдера"><InspectorScalar value={error.providerCode} /></InspectorFieldRow> : null}
    {error?.retryable !== undefined ? <InspectorFieldRow label="Можно повторить"><InspectorStatus label={error.retryable ? 'Да' : 'Нет'} tone={error.retryable ? 'warn' : 'neutral'} /></InspectorFieldRow> : null}
    {error?.retryAfterMs !== undefined ? <InspectorFieldRow label="Повтор через"><InspectorScalar value={formatCallDuration(error.retryAfterMs)} /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Повторы"><InspectorScalar value={call.info.retryCount} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function CallInfoView({ call }: { call: TraceCall }) {
  const request = call.requestView;
  const status = callStatusPresentation(call.info.status);
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={status.label} tone={status.tone} /></InspectorFieldRow>
    {request.model ? <InspectorFieldRow label="Модель"><InspectorScalar value={request.model} /></InspectorFieldRow> : null}
    {request.purpose ? <InspectorFieldRow label="Назначение"><InspectorScalar value={request.purpose} /></InspectorFieldRow> : null}
    {request.toolName ? <InspectorFieldRow label="Операция"><InspectorScalar value={callDisplayName(request.toolName)} /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Длительность"><InspectorScalar value={formatCallDuration(call.info.durationMs)} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function ToolInfoView({ call, toolNames, description }: { call: TraceCall; toolNames?: ToolNameMap; description?: string }) {
  const request = call.requestView;
  const status = callStatusPresentation(call.info.status);
  const task = request.description ?? description ?? '—';
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={status.label} tone={status.tone} /></InspectorFieldRow>
    <InspectorFieldRow label="Название тулза"><InspectorScalar value={callDisplayName(request.toolName ?? '', toolNames)} /></InspectorFieldRow>
    <InspectorFieldRow label="Задача"><InspectorTextBlock text={task} /></InspectorFieldRow>
    <InspectorFieldRow label="Длительность"><InspectorScalar value={formatCallDuration(call.info.durationMs)} /></InspectorFieldRow>
  </InspectorFieldGroup>;
}

export function LlmRequestSnapshotView({ call }: { call: TraceCall }) {
  const messages = call.requestView.messages;
  const request = call.requestView;
  const roleLabel = (role: string): string => ({ system: 'Система', user: 'Пользователь', assistant: 'Ассистент', tool: 'Инструмент' }[role] ?? formatFieldLabel(role));
  return <div className={styles.messages}>
    <InspectorFieldGroup>
      {request.temperature !== undefined ? <InspectorFieldRow label="Температура"><InspectorScalar value={request.temperature} /></InspectorFieldRow> : null}
      {request.maxTokens !== undefined ? <InspectorFieldRow label="Лимит токенов"><InspectorScalar value={request.maxTokens} /></InspectorFieldRow> : null}
      {request.requestBytes !== undefined ? <InspectorFieldRow label="Размер запроса"><InspectorScalar value={`${request.requestBytes} B`} /></InspectorFieldRow> : null}
      {request.inputTokensEstimate !== undefined ? <InspectorFieldRow label="Оценка входных токенов"><InspectorScalar value={request.inputTokensEstimate} /></InspectorFieldRow> : null}
      {request.responseSchemaBytes !== undefined ? <InspectorFieldRow label="Размер response schema"><InspectorScalar value={`${request.responseSchemaBytes} B`} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    {messages.length ? messages.map((message, index) => <div key={`${message.role}:${index}`} className={`${styles.message} ${styles[message.role] ?? ''}`}><div className={styles.messageHeader}><span>{roleLabel(message.role)}</span>{message.role === 'system' ? <span>системный контекст</span> : null}</div><Value value={message.content.data ?? message.content.text} structured /></div>) : <InspectorFieldGroup><InspectorFieldRow label="Сообщения">Нет данных</InspectorFieldRow></InspectorFieldGroup>}
  </div>;
}

export function LlmResponseSnapshotView({ call, toolNames }: { call: TraceCall; toolNames?: ToolNameMap }) {
  const response = call.responseView;
  if (!response) return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label="Ожидается" tone="warn" /></InspectorFieldRow></InspectorFieldGroup>;
  if (call.info.status === 'waiting_retry') return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label="Ожидает повтора" tone="warn" /></InspectorFieldRow>{call.errorView?.retryAfterMs !== undefined ? <InspectorFieldRow label="Повтор через"><InspectorScalar value={formatCallDuration(call.errorView.retryAfterMs)} /></InspectorFieldRow> : null}</InspectorFieldGroup>;
  if (call.info.status === 'error') return <InspectorFieldGroup><InspectorFieldRow label="Результат"><InspectorScalar value="Нет результата" /></InspectorFieldRow></InspectorFieldGroup>;
  const semanticOutcome = call.info.outcome;
  const parsed = response.content;
  const metadata = <InspectorFieldGroup>
    {response.resultKind !== undefined ? <InspectorFieldRow label="Тип результата"><InspectorScalar value={response.resultKind} /></InspectorFieldRow> : null}
    {response.responseLength !== undefined ? <InspectorFieldRow label="Размер ответа"><InspectorScalar value={`${response.responseLength} B`} /></InspectorFieldRow> : null}
    {response.terminal !== undefined ? <InspectorFieldRow label="Терминальный"><InspectorScalar value={response.terminal ? 'Да' : 'Нет'} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
  if (semanticOutcome?.kind === 'tools') {
    if (response.toolCall) {
      return <div className={styles.list}>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Выбранная операция">{callDisplayName(response.toolCall.name, toolNames)}</InspectorFieldRow><InspectorFieldRow label="Аргументы"><Value value={response.toolCall.arguments ?? {}} /></InspectorFieldRow></InspectorFieldGroup></div>;
    }
    return <div className={styles.list}>{metadata}
      <InspectorFieldGroup><InspectorFieldRow label="Результат"><InspectorStatus label={semanticOutcome.count ? `${semanticOutcome.label} · ${semanticOutcome.count}` : semanticOutcome.label} tone="info" /></InspectorFieldRow></InspectorFieldGroup>
      {response.linkedToolCalls.map((toolCall, index) => <div key={`${toolCall.name}:${index}`} className={styles.listItem}>
        <div className={styles.listTitle}>{callDisplayName(toolCall.name, toolNames)}</div>
        <ToolRequest value={toolCall.arguments} />
      </div>)}
    </div>;
  }
  if (semanticOutcome?.kind === 'plan') return <div className={styles.list}>{metadata}<PlanView plan={call.plan} /></div>;
  if (response.toolCall) {
    return <div className={styles.list}>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Выбранная операция">{callDisplayName(response.toolCall.name, toolNames)}</InspectorFieldRow><InspectorFieldRow label="Аргументы"><Value value={response.toolCall.arguments ?? {}} /></InspectorFieldRow></InspectorFieldGroup></div>;
  }
  if (parsed?.kind === 'json') return <div className={styles.list}>{metadata}<Value value={parsed.data} /></div>;
  return <div className={styles.list}>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Ответ"><Value value={parsed?.text} /></InspectorFieldRow></InspectorFieldGroup></div>;
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
  return <ToolRequest value={call.requestView.arguments} />;
}

export function ToolResponse({ call }: { call: TraceCall }) {
  const presentation = call.info;
  const result = call.responseView?.toolResult;
  if (!result) return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label={presentation.status === 'waiting_retry' ? 'Ожидает повтора' : 'Ожидается'} tone="warn" /></InspectorFieldRow></InspectorFieldGroup>;
  return <div className={styles.list}>
    <div className={`${styles.summary} ${presentation.status === 'error' ? styles.failure : styles.success}`}><Fields entries={result.details} />{result.message ? <InspectorTextBlock text={result.message} /> : null}</div>
    {typeof result.data === 'string' && result.data ? <InspectorFieldGroup><InspectorFieldRow label="Предпросмотр результата"><InspectorTextBlock text={result.data} /></InspectorFieldRow>{result.truncated ? <InspectorFieldRow label="Результат">Сокращён</InspectorFieldRow> : null}</InspectorFieldGroup> : null}
    {result.items.map((item, index) => <div key={index} className={styles.listItem}><div className={styles.listTitle}>{item.title}</div><Fields entries={item.fields} /></div>)}
    {!result.items.length && result.data !== undefined && result.data !== null && typeof result.data !== 'string' ? <div className={styles.summary}><Fields entries={result.details} /></div> : null}
    <ExtractionResultViewer extraction={call.extraction} />
  </div>;
}

export const ToolResponseView = ToolResponse;
