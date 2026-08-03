import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceCall } from '../../traceProjection';
import { callDisplayName, llmMessages, llmOutcome, llmResponseContent, llmResponseStatus, parseCallContent, purposeLabel, toDisplayEntries, toolResult, type DisplayEntry, type ToolNameMap } from '../../callInspection';
import styles from './CallViews.module.css';

function Value({ value, structured = false }: { value: unknown; structured?: boolean }) {
  if (value === null || value === undefined || typeof value === 'boolean' || typeof value === 'number') return <InspectorScalar value={value as string | number | boolean | null | undefined} />;
  if (typeof value === 'string' && !structured) return <InspectorScalar value={value} />;
  const parsed = structured ? parseCallContent(value) : { kind: 'json' as const, data: value };
  if (parsed.kind === 'text') return <InspectorTextBlock text={parsed.text ?? '—'} />;
  if (parsed.data === null || parsed.data === undefined || typeof parsed.data === 'boolean' || typeof parsed.data === 'number') return <InspectorScalar value={parsed.data as number | boolean | null | undefined} />;
  return <InspectorJsonBlock value={parsed.data ?? '—'} />;
}

function Fields({ entries }: { entries: DisplayEntry[] }) {
  return <InspectorFieldGroup>{entries.length ? entries.map((entry) => <InspectorFieldRow key={entry.label} label={entry.label}><Value value={entry.value} /></InspectorFieldRow>) : <InspectorFieldRow label="Данные">—</InspectorFieldRow>}</InspectorFieldGroup>;
}

export function CallInfoView({ call, toolNames }: { call: TraceCall; toolNames?: ToolNameMap }) {
  const request = call.request.payload;
  const response = call.response?.payload ?? {};
  const toolOutcome = call.kind === 'tool' && call.response ? toolResult(response) : undefined;
  const semanticOutcome = call.kind === 'llm' && call.response ? llmOutcome(response, call.toolCallCount) : undefined;
  const entries = call.kind === 'llm'
    ? [
        { label: 'Статус', value: !call.response ? 'Ожидается' : semanticOutcome?.count ? `${semanticOutcome.label} · ${semanticOutcome.count}` : semanticOutcome?.label },
        { label: 'Назначение', value: purposeLabel(request.purpose) },
        { label: 'Модель', value: request.model ?? response.model },
        { label: 'Сообщений', value: Array.isArray(request.messages) ? request.messages.length : undefined },
        { label: 'Токены входа', value: response.tokens_in }, { label: 'Токены выхода', value: response.tokens_out },
        { label: 'Длительность', value: response.duration_ms ? `${Number(response.duration_ms) / 1000} с` : undefined },
      ].filter((entry) => entry.value !== undefined && entry.value !== null && entry.value !== '')
    : call.kind === 'tool'
      ? [
          { label: 'Операция', value: callDisplayName(String(request.tool ?? ''), toolNames) },
          { label: 'Статус', value: !call.response ? 'Ожидается' : toolOutcome?.success === true ? 'Успешно' : toolOutcome?.success === false ? 'Ошибка' : 'Нет результата' },
          ...toDisplayEntries({ reused: response.reused, truncated: response.truncated }),
        ]
      : toDisplayEntries(request);
  return <Fields entries={entries} />;
}

export function LlmRequestView({ call }: { call: TraceCall }) {
  const messages = llmMessages(call.request.payload);
  return <div className={styles.messages}>{messages.length ? messages.map((message, index) => <div key={`${message.role}:${index}`} className={`${styles.message} ${styles[message.role] ?? ''}`}><div className={styles.messageHeader}><span>{message.role}</span>{message.role === 'system' ? <span>системный контекст</span> : null}</div><Value value={message.content.data ?? message.content.text} structured /></div>) : <Fields entries={toDisplayEntries(call.request.payload)} />}</div>;
}

export function LlmResponseView({ call, toolNames }: { call: TraceCall; toolNames?: ToolNameMap }) {
  const payload = call.response?.payload;
  if (!payload) return <InspectorFieldGroup><InspectorFieldRow label="Статус">Ожидается</InspectorFieldRow></InspectorFieldGroup>;
  const responseStatus = llmResponseStatus(payload);
  if (responseStatus === 'error') return <InspectorFieldGroup><InspectorFieldRow label="Статус">Ошибка</InspectorFieldRow><InspectorFieldRow label="Тип ошибки">{String(payload.error_type)}</InspectorFieldRow></InspectorFieldGroup>;
  const semanticOutcome = llmOutcome(payload, call.toolCallCount);
  if (semanticOutcome.kind === 'tools' || responseStatus === 'empty') return <InspectorFieldGroup><InspectorFieldRow label="Статус">{semanticOutcome.count ? `${semanticOutcome.label} · ${semanticOutcome.count}` : semanticOutcome.label}</InspectorFieldRow></InspectorFieldGroup>;
  const parsed = parseCallContent(llmResponseContent(payload));
  if (parsed.kind === 'tool_call') {
    const toolCall = parsed.data as Record<string, unknown>;
    return <InspectorFieldGroup><InspectorFieldRow label="Выбранная операция">{callDisplayName(String(toolCall.tool ?? '—'), toolNames)}</InspectorFieldRow><InspectorFieldRow label="Аргументы"><Value value={toolCall.arguments ?? {}} /></InspectorFieldRow></InspectorFieldGroup>;
  }
  if (parsed.kind === 'json') return <Fields entries={toDisplayEntries(parsed.data)} />;
  return <InspectorFieldGroup><InspectorFieldRow label="Ответ"><Value value={parsed.text} /></InspectorFieldRow></InspectorFieldGroup>;
}

export function ToolRequestView({ call }: { call: TraceCall }) {
  return <Fields entries={toDisplayEntries(call.request.payload.arguments)} />;
}

export function ToolResponseView({ call }: { call: TraceCall }) {
  if (!call.response) return <InspectorFieldGroup><InspectorFieldRow label="Статус">Ожидается</InspectorFieldRow></InspectorFieldGroup>;
  const result = toolResult(call.response.payload);
  const isTruncated = call.response.payload.truncated === true;
  const items = Array.isArray(result.data) ? result.data : Array.isArray((result.data as Record<string, unknown>)?.templates) ? (result.data as Record<string, unknown>).templates as unknown[] : Array.isArray((result.data as Record<string, unknown>)?.hits) ? (result.data as Record<string, unknown>).hits as unknown[] : [];
  return <div className={styles.list}>
    <div className={`${styles.summary} ${result.success === false ? styles.failure : styles.success}`}><Fields entries={result.details} />{result.message ? <InspectorTextBlock text={result.message} /> : null}</div>
    {typeof result.data === 'string' && result.data ? <InspectorFieldGroup><InspectorFieldRow label="Предпросмотр результата"><InspectorTextBlock text={result.data} /></InspectorFieldRow>{isTruncated ? <InspectorFieldRow label="Результат">Сокращён</InspectorFieldRow> : null}</InspectorFieldGroup> : null}
    {items.map((item, index) => { const entry = item as Record<string, unknown>; return <div key={index} className={styles.listItem}><div className={styles.listTitle}>{String(entry.title ?? entry.primary_fragment ?? entry.name ?? `Элемент ${index + 1}`)}</div><Fields entries={toDisplayEntries(entry.row_data ?? entry)} /></div>; })}
    {!items.length && result.data !== undefined && result.data !== null && typeof result.data !== 'string' ? <div className={styles.summary}><Fields entries={toDisplayEntries(result.data)} /></div> : null}
  </div>;
}
