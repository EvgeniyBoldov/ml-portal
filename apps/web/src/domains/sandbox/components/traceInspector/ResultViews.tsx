import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceExecutorResult, TraceExecutorRun, TraceStage, TraceStep } from '../../traceProjection';
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
  return <ExecutorResultCard result={executor.result} />;
}

export const AgentResultViewer = ExecutorResultView;
export const SynthesizerResultViewer = ExecutorResultView;

export function StageResultView({ stage }: { stage: TraceStage }) {
  const results = stage.executorRuns.map((executor) => executor.result);
  return <div className={styles.list}>{results.length ? results.map((result, index) => <ExecutorResultCard key={`${result.name}:${index}`} result={result} />) : <InspectorFieldGroup><InspectorFieldRow label="Результат">Исполнители ещё не запускались.</InspectorFieldRow></InspectorFieldGroup>}</div>;
}

/** Shows only the executor results that belong to the selected logical step. */
export function StepResultView({ step }: { step: TraceStep }) {
  const results = step.executorRuns.map((executor) => executor.result);
  return <div className={styles.list}>{results.length ? results.map((result, index) => <ExecutorResultCard key={`${result.name}:${index}`} result={result} />) : <InspectorFieldGroup><InspectorFieldRow label="Результат">Исполнители этого шага ещё не запускались.</InspectorFieldRow></InspectorFieldGroup>}</div>;
}
