import { useEffect, useMemo, useState } from 'react';
import type { SandboxTraceState } from '../traceState';
import type { RuntimeProgress } from '../types';
import { projectTraceStages, stepFor, traceElapsedMs, type TraceCall, type TraceExecutorRun, type TraceInspectionTarget, type TraceMetrics, type TraceStage } from '../traceProjection';
import { llmOutcome, toolResult } from '../callInspection';
import { normalizeTraceStatus, traceStatusLabel } from '../traceStatus';
import styles from './ExecutionTrace.module.css';

interface ExecutionTraceProps {
  trace: SandboxTraceState;
  isRunning: boolean;
  progress?: RuntimeProgress[];
  onSelectTarget?: (target: TraceInspectionTarget) => void;
  selectedTargetKey?: string | null;
}

const formatDuration = (ms: number | undefined): string => {
  if (!ms) return '0 с';
  return `${Math.max(1, Math.round(ms / 1000))} с`;
};

function downloadTraceLog(trace: SandboxTraceState, progress: RuntimeProgress[], elapsedMs: number | undefined): void {
  const events = trace.eventIdsBySequence
    .map((eventId) => trace.eventsById[eventId])
    .filter(Boolean);
  const lines = [
    'TRACE LOG EXPORT',
    `run_id: ${trace.runId ?? 'unknown'}`,
    `exported_at: ${new Date().toISOString()}`,
    `elapsed: ${formatDuration(elapsedMs)}`,
    `events: ${events.length}`,
    `progress_items: ${progress.length}`,
    '',
    '=== RAW JOURNAL EVENTS ===',
    ...events.map((event) => JSON.stringify(event, null, 2)),
    '',
    '=== RAW PROGRESS ===',
    ...progress.map((item) => JSON.stringify(item, null, 2)),
    '',
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `trace-${trace.runId ?? 'unknown'}-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function StatusBadge({ status }: { status: string }) {
  const normalizedStatus = normalizeTraceStatus(status);
  const normalized = normalizedStatus === 'completed' ? 'complete' : normalizedStatus === 'failed' || normalizedStatus === 'unfulfillable' ? 'fail' : normalizedStatus;
  const label = traceStatusLabel(status);
  return <span className={`${styles.status} ${styles[`status-${normalized}`] ?? ''}`}>{label}</span>;
}

function statusClass(status: string): string {
  if (status === 'completed' || status === 'complete') return styles.executorComplete;
  if (status === 'failed' || status === 'fail' || status === 'error' || status === 'unfulfillable' || status === 'stalled') return styles.executorFailed;
  if (status === 'waiting' || status === 'waiting_input') return styles.executorWaiting;
  if (status === 'paused') return styles.executorWaiting;
  return styles.executorRunning;
}

function Metrics({ metrics, hideElapsed }: { metrics: TraceMetrics; hideElapsed?: boolean }) {
  if ((!metrics.elapsedMs || hideElapsed) && !metrics.tokens && !metrics.retries) return null;
  return (
    <div className={styles.metrics}>
      {metrics.tokens ? <span>tokens: {metrics.tokens}</span> : null}
      {!hideElapsed && metrics.elapsedMs ? <span>time: {formatDuration(metrics.elapsedMs)}</span> : null}
      {metrics.retries ? <span>retry: {metrics.retries}</span> : null}
    </div>
  );
}

function CallCard({ call, executor, stage, onSelect, selected }: { call: TraceCall; executor: TraceExecutorRun; stage: TraceStage; onSelect?: (target: TraceInspectionTarget) => void; selected?: boolean }) {
  const typeLabel = {
    llm: 'LLM',
    tool: 'TOOL',
    clarify: 'УТОЧНЕНИЕ',
    confirm: 'ПОДТВЕРЖДЕНИЕ',
    error: 'ОШИБКА',
  }[call.kind];
  const toolFailed = call.kind === 'tool' && call.response ? toolResult(call.response.payload).success === false : false;
  const outcome = call.kind === 'llm' && call.response ? llmOutcome(call.response.payload, call.toolCallCount) : undefined;
  const llmFailed = outcome?.kind === 'error';
  const statusLabel = call.kind === 'error' || toolFailed || llmFailed
    ? 'Ошибка'
    : call.response
      ? (call.kind === 'llm' ? outcome?.label ?? 'Ответ' : call.kind === 'tool' ? 'Результат' : 'Ответ получен')
      : call.kind === 'clarify' ? 'Ожидает ответ' : call.kind === 'confirm' ? 'Ожидает решения' : 'Выполняется';
  return (
    <div className={styles.callWrap}>
      <button type="button" className={`${styles.call} ${styles[`call-${call.kind}`]} ${selected ? styles.isSelected : ''}`} onClick={() => onSelect?.(call.kind === 'error' ? { kind: 'error', key: call.entity.key, call, executor, stage } : { kind: 'call', key: call.entity.key, call, executor, stage })}>
        <span className={styles.callType}><i className={styles.typeMarker} />{typeLabel}</span>
        <span className={styles.callTitle}>{call.title}{call.summary ? <small>{call.summary}</small> : null}</span>
        <span className={`${styles.callStatus} ${call.kind === 'error' || toolFailed || llmFailed ? styles.callStatusError : outcome?.kind === 'empty' ? styles.callStatusWarning : call.response ? styles.callStatusComplete : styles.callStatusRunning}`}><span>{statusLabel}</span>{outcome?.count ? <span className={styles.callStatusCount}>· {outcome.count}</span> : null}</span>
      </button>
    </div>
  );
}

function CallSummary({ calls }: { calls: TraceCall[] }) {
  const counts = calls.reduce<Record<string, number>>((result, call) => ({ ...result, [call.kind]: (result[call.kind] ?? 0) + 1 }), {});
  const labels: Array<[TraceCall['kind'], string]> = [['llm', 'LLM'], ['tool', 'tool'], ['clarify', 'уточнение'], ['confirm', 'подтверждение'], ['error', 'ошибка']];
  return <span className={styles.callSummary}>{labels.filter(([kind]) => counts[kind]).map(([kind, label]) => <span key={kind} className={styles[`summary-${kind}`]}>{counts[kind]} {label}</span>)}</span>;
}

function ExecutorRunCard({ executor, stage, onSelect, selectedTargetKey }: { executor: TraceExecutorRun; stage: TraceStage; onSelect?: (target: TraceInspectionTarget) => void; selectedTargetKey?: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const isTerminal = ['completed', 'complete', 'failed', 'fail', 'error', 'stalled'].includes(executor.entity.status);
  return (
    <article className={`${styles.executor} ${statusClass(executor.entity.status)} ${selectedTargetKey === executor.entity.key ? styles.isSelected : ''}`}>
      <div className={styles.executorBody}>
        <button type="button" className={styles.executorLabel} onClick={() => onSelect?.({ kind: 'executor_run', key: executor.entity.key, executor, stage })}>
          <span className={styles.executorType}>{executor.executorType}</span>
          <span className={styles.executorName}>{executor.executorName}<small>{executor.task}</small></span>
          {executor.calls.length > 0 ? <CallSummary calls={executor.calls} /> : null}
          <span className={styles.executorStatus}><StatusBadge status={executor.entity.status} /></span>
        </button>
        <button
          type="button"
          className={styles.executorExpand}
          aria-label={expanded ? 'Скрыть вызовы исполнителя' : 'Показать вызовы исполнителя'}
          aria-expanded={expanded}
          disabled={executor.calls.length === 0}
          onClick={() => setExpanded((value) => !value)}
        >⌄</button>
      </div>
      <Metrics metrics={executor.metrics} hideElapsed={isTerminal} />
      {expanded && executor.calls.length > 0 && <div className={styles.callList}>{executor.calls.map((call) => <CallCard key={call.entity.key} call={call} executor={executor} stage={stage} onSelect={onSelect} selected={selectedTargetKey === call.entity.key} />)}</div>}
    </article>
  );
}

function StepCard({ step, onSelect, selectedTargetKey }: { step: ReturnType<typeof stepFor>; onSelect?: (target: TraceInspectionTarget) => void; selectedTargetKey?: string | null }) {
  const { stage } = step;
  return (
    <div className={styles.stageRow}>
      <button type="button" className={`${styles.stageNumber} ${selectedTargetKey === step.key ? styles.isSelected : ''}`} onClick={() => onSelect?.({ kind: 'step', key: step.key, step })}>{step.number || stage.iterationNumber || 1}</button>
      <div className={styles.stage}>
        <div className={styles.executorList}>{step.executorRuns.map((executor) => <ExecutorRunCard key={executor.entity.key} executor={executor} stage={stage} onSelect={onSelect} selectedTargetKey={selectedTargetKey} />)}</div>
      </div>
    </div>
  );
}

function StageCard({ stage, onSelect, selectedTargetKey }: { stage: TraceStage; onSelect?: (target: TraceInspectionTarget) => void; selectedTargetKey?: string | null }) {
  const steps = stage.steps.length > 0 ? stage.steps : [stepFor(stage)];
  return <div className={styles.stepList}>{steps.map((step) => <StepCard key={step.key} step={step} onSelect={onSelect} selectedTargetKey={selectedTargetKey} />)}</div>;
}

export function ExecutionTrace({ trace, isRunning, progress = [], onSelectTarget, selectedTargetKey }: ExecutionTraceProps) {
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const stages = useMemo(() => projectTraceStages(trace), [trace]);
  const latestProgress = progress[progress.length - 1]?.description;
  useEffect(() => {
    if (!isRunning) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isRunning]);
  if (stages.length === 0 && !latestProgress) return null;
  const elapsedMs = traceElapsedMs(trace, now);
  return (
    <section className={styles.trace}>
      <header className={styles.summary}>
        <button type="button" className={styles.summaryToggle} onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          <span className={styles.summaryTitle}>Трейс выполнения ({formatDuration(elapsedMs)})</span>
          {isRunning && <span className={styles.running}>выполняется</span>}
          {latestProgress ? <span className={styles.progress}>{latestProgress}</span> : null}
          <span className={`${styles.chevron} ${expanded ? styles.chevronOpen : ''}`}>⌄</span>
        </button>
        <button
          type="button"
          className={styles.download}
          onClick={() => downloadTraceLog(trace, progress, elapsedMs)}
          disabled={trace.eventIdsBySequence.length === 0 && progress.length === 0}
          title="Скачать все raw-события и progress текущего трейса"
        >
          ↓ Скачать лог
        </button>
      </header>
      {expanded && <div className={styles.iterations}>{stages.map((stage) => (
        <article key={stage.entity.key} className={`${styles.iteration} ${styles[`iteration-${stage.iterationType}`] ?? ''} ${selectedTargetKey === stage.entity.key ? styles.isSelected : ''}`}>
          <header className={styles.iterationHeader}>
            <button type="button" className={styles.iterationType} onClick={() => onSelectTarget?.({ kind: 'iteration', key: stage.entity.key, stage })}>
              {stage.label}
            </button>
            <span className={styles.iterationTask}>{stage.task}</span>
            <StatusBadge status={stage.entity.status} />
          </header>
          <div className={styles.iterationBody}><StageCard stage={stage} onSelect={onSelectTarget} selectedTargetKey={selectedTargetKey} /></div>
        </article>
      ))}</div>}
    </section>
  );
}
