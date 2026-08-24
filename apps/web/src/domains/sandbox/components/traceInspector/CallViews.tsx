import { InspectorExpandableValue, InspectorFieldGroup, InspectorFieldRow, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceCall } from '../../traceProjection';
import { callDisplayName, type ToolNameMap } from '../../callInspection';
import { callStatusPresentation, formatCallDuration } from '../../callPresentation';
import { ExtractionResultViewer } from './viewers/ExtractionResultViewer';
import { PlanView } from './TraceDataViews';
import { InspectorStack } from './InspectorPrimitives';
import styles from './CallViews.module.css';

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
  const request = call.requestView;
  return <InspectorStack>
    <InspectorFieldGroup>
      {request.temperature !== undefined ? <InspectorFieldRow label="Температура"><InspectorScalar value={request.temperature} /></InspectorFieldRow> : null}
      {request.maxTokens !== undefined ? <InspectorFieldRow label="Лимит токенов"><InspectorScalar value={request.maxTokens} /></InspectorFieldRow> : null}
      {request.requestBytes !== undefined ? <InspectorFieldRow label="Размер запроса"><InspectorScalar value={`${request.requestBytes} B`} /></InspectorFieldRow> : null}
      {request.inputTokensEstimate !== undefined ? <InspectorFieldRow label="Оценка входных токенов"><InspectorScalar value={request.inputTokensEstimate} /></InspectorFieldRow> : null}
      {request.responseSchemaBytes !== undefined ? <InspectorFieldRow label="Размер response schema"><InspectorScalar value={`${request.responseSchemaBytes} B`} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    <InspectorFieldGroup>
      <InspectorFieldRow label="Контекст вызова">
        {request.messageTranscript
          ? <InspectorExpandableValue value={request.messageTranscript} title="Контекст LLM-вызова" />
          : <InspectorScalar value="Нет сообщений" />}
      </InspectorFieldRow>
    </InspectorFieldGroup>
  </InspectorStack>;
}

export function LlmResponseSnapshotView({ call, toolNames }: { call: TraceCall; toolNames?: ToolNameMap }) {
  const response = call.responseView;
  if (!response) return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label="Ожидается" tone="warn" /></InspectorFieldRow></InspectorFieldGroup>;
  if (call.info.status === 'waiting_retry') return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label="Ожидает повтора" tone="warn" /></InspectorFieldRow>{call.errorView?.retryAfterMs !== undefined ? <InspectorFieldRow label="Повтор через"><InspectorScalar value={formatCallDuration(call.errorView.retryAfterMs)} /></InspectorFieldRow> : null}</InspectorFieldGroup>;
  if (call.info.status === 'error') return <InspectorFieldGroup><InspectorFieldRow label="Результат"><InspectorScalar value="Нет результата" /></InspectorFieldRow></InspectorFieldGroup>;
  const semanticOutcome = call.info.outcome;
  const parsed = response.content;
  const metadata = <InspectorFieldGroup>
    {semanticOutcome ? <InspectorFieldRow label="Результат"><InspectorStatus label={semanticOutcome.count ? `${semanticOutcome.label} · ${semanticOutcome.count}` : semanticOutcome.label} tone="info" /></InspectorFieldRow> : null}
    {response.responseLength !== undefined ? <InspectorFieldRow label="Размер ответа"><InspectorScalar value={`${response.responseLength} B`} /></InspectorFieldRow> : null}
    {response.terminal !== undefined ? <InspectorFieldRow label="Терминальный"><InspectorScalar value={response.terminal ? 'Да' : 'Нет'} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
  if (semanticOutcome?.kind === 'tools') {
    const calls = response.toolCall ? [response.toolCall] : response.linkedToolCalls;
    return <InspectorStack>{metadata}<InspectorFieldGroup>
      <InspectorFieldRow label="Запрошенные операции"><InspectorScalar value={calls.length ? calls.map((toolCall) => callDisplayName(toolCall.name, toolNames)).join(', ') : 'Нет данных'} /></InspectorFieldRow>
    </InspectorFieldGroup></InspectorStack>;
  }
  if (semanticOutcome?.kind === 'plan') return <InspectorStack>{metadata}<PlanView plan={call.plan} /></InspectorStack>;
  const answer = parsed?.kind === 'text' ? parsed.text : parsed?.data;
  return <InspectorStack>{metadata}<InspectorFieldGroup><InspectorFieldRow label="Ответ модели">
    {answer === undefined ? <InspectorScalar value="Нет данных" /> : <InspectorExpandableValue value={answer} title="Ответ LLM" />}
  </InspectorFieldRow></InspectorFieldGroup></InspectorStack>;
}

export const LlmRequestView = LlmRequestSnapshotView;
export const LlmResponseView = LlmResponseSnapshotView;

export function ToolRequest({ value }: { value: unknown }) {
  const empty = value === undefined || value === null || (typeof value === 'object' && !Array.isArray(value) && !Object.keys(value).length);
  return <InspectorFieldGroup><InspectorFieldRow label="Аргументы">
    {empty ? <InspectorScalar value="Нет аргументов" /> : <InspectorExpandableValue value={value} title="Аргументы tool-вызова" />}
  </InspectorFieldRow></InspectorFieldGroup>;
}

export function ToolRequestView({ call }: { call: TraceCall }) {
  return <ToolRequest value={call.requestView.arguments} />;
}

export function ToolResponse({ call }: { call: TraceCall }) {
  const presentation = call.info;
  const result = call.responseView?.toolResult;
  if (!result) return <InspectorFieldGroup><InspectorFieldRow label="Статус"><InspectorStatus label={presentation.status === 'waiting_retry' ? 'Ожидает повтора' : 'Ожидается'} tone="warn" /></InspectorFieldRow></InspectorFieldGroup>;
  return <InspectorStack><InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={result.success === false ? 'Ошибка' : 'Успешно'} tone={result.success === false ? 'danger' : 'success'} /></InspectorFieldRow>
    <InspectorFieldRow label="Краткий результат"><InspectorScalar value={result.summary} /></InspectorFieldRow>
    {result.message ? <InspectorFieldRow label="Сообщение"><InspectorExpandableValue value={result.message} title="Сообщение tool-вызова" /></InspectorFieldRow> : null}
    {result.data !== undefined && result.data !== null ? <InspectorFieldRow label="Данные"><InspectorExpandableValue value={result.data} title="Результат tool-вызова" /></InspectorFieldRow> : null}
    {result.truncated ? <InspectorFieldRow label="Данные"><InspectorStatus label="Сокращены" tone="warn" /></InspectorFieldRow> : null}
  </InspectorFieldGroup>
    <ExtractionResultViewer extraction={call.extraction} />
  </InspectorStack>;
}

export const ToolResponseView = ToolResponse;
