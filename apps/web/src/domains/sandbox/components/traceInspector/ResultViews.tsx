import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceExecutorResult, TraceExecutorRun, TraceStage, TraceStep } from '../../traceProjection';
import { InspectorEmptyState, InspectorStack } from './InspectorPrimitives';
import styles from './ResultViews.module.css';

function tone(status: TraceExecutorResult['status']): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (status === 'completed') return 'success';
  if (status === 'failed' || status === 'unfulfillable' || status === 'aborted') return 'danger';
  if (status === 'waiting' || status === 'paused') return 'warn';
  return 'info';
}

function Output({ value }: { value: unknown }) {
  if (typeof value === 'string') return <InspectorTextBlock text={value} />;
  if (value === null || typeof value === 'number' || typeof value === 'boolean') return <InspectorScalar value={value} />;
  return <InspectorJsonBlock value={value} />;
}

const completionKindLabel = (value: string): string => ({ answer: 'Ответ', completed: 'Завершено', plan: 'План', failed: 'Ошибка' }[value] ?? value);

function ExecutorResultFields({ result }: { result: TraceExecutorResult }) {
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={result.statusLabel} tone={tone(result.status)} /></InspectorFieldRow>
    {result.completionKind ? <InspectorFieldRow label="Тип завершения"><InspectorScalar value={completionKindLabel(result.completionKind)} /></InspectorFieldRow> : null}
    {result.sufficientForPhase !== undefined ? <InspectorFieldRow label="Достаточно для этапа"><InspectorScalar value={result.sufficientForPhase} /></InspectorFieldRow> : null}
    {result.message ? <InspectorFieldRow label="Итог"><InspectorTextBlock text={result.message} /></InspectorFieldRow> : null}
    {result.output !== undefined ? <InspectorFieldRow label="Результат"><Output value={result.output} /></InspectorFieldRow> : null}
    {result.missingInputs !== undefined ? <InspectorFieldRow label="Недостающие входные данные"><Output value={result.missingInputs} /></InspectorFieldRow> : null}
    {result.needs !== undefined ? <InspectorFieldRow label="Потребности"><Output value={result.needs} /></InspectorFieldRow> : null}
    {result.artifacts !== undefined ? <InspectorFieldRow label="Артефакты"><Output value={result.artifacts} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}

function ExecutorResultCard({ result }: { result: TraceExecutorResult }) {
  const operations = result.operations;
  return <article className={styles.card}>
    <div className={styles.cardHeader}><span className={styles.name}>{result.name}</span><Badge size="small" tone={tone(result.status)}>{result.statusLabel}</Badge></div>
    {operations.total ? <div className={styles.operations}>Операции: {operations.total}, успешно: {operations.succeeded}, с ошибкой: {operations.failed}</div> : null}
    {result.completionKind ? <InspectorFieldGroup><InspectorFieldRow label="Тип завершения"><InspectorScalar value={result.completionKind} /></InspectorFieldRow>
      {result.sufficientForPhase !== undefined ? <InspectorFieldRow label="Достаточно для этапа"><InspectorScalar value={result.sufficientForPhase ? 'Да' : 'Нет'} /></InspectorFieldRow> : null}
    </InspectorFieldGroup> : null}
    {result.message ? <div className={styles.message}><InspectorTextBlock text={result.message} /></div> : null}
    {result.output !== undefined ? <div className={styles.output}><Output value={result.output} /></div> : null}
    {result.missingInputs !== undefined ? <InspectorFieldGroup><InspectorFieldRow label="Недостающие входные данные"><Output value={result.missingInputs} /></InspectorFieldRow></InspectorFieldGroup> : null}
    {result.needs !== undefined ? <InspectorFieldGroup><InspectorFieldRow label="Потребности"><Output value={result.needs} /></InspectorFieldRow></InspectorFieldGroup> : null}
    {result.artifacts !== undefined ? <InspectorFieldGroup><InspectorFieldRow label="Артефакты"><Output value={result.artifacts} /></InspectorFieldRow></InspectorFieldGroup> : null}
    {!result.message && result.output === undefined && !operations.total ? <div className={styles.empty}>Исполнитель не записал содержательный результат.</div> : null}
  </article>;
}

export function ExecutorResultView({ executor }: { executor: TraceExecutorRun }) {
  return <ExecutorResultFields result={executor.result} />;
}

export const AgentResultViewer = ExecutorResultView;
export const SynthesizerResultViewer = ExecutorResultView;

export function StageResultView({ stage }: { stage: TraceStage }) {
  const results = stage.executorRuns.map((executor) => executor.result);
  return <InspectorStack>{results.length ? results.map((result, index) => <ExecutorResultCard key={`${result.name}:${index}`} result={result} />) : <InspectorEmptyState message="Исполнители ещё не запускались." />}</InspectorStack>;
}

/** Shows only the executor results that belong to the selected logical step. */
export function StepResultView({ step }: { step: TraceStep }) {
  const results = step.executorRuns.map((executor) => executor.result);
  return <InspectorStack>{results.length ? results.map((result, index) => <ExecutorResultCard key={`${result.name}:${index}`} result={result} />) : <InspectorEmptyState message="Исполнители этого шага ещё не запускались." />}</InspectorStack>;
}
