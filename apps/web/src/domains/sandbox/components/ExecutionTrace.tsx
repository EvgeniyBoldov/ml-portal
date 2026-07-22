import { useEffect, useMemo, useState } from 'react';
import type { SandboxTraceState } from '../traceState';
import { projectTraceStages, stepFor, traceElapsedMs, type TraceCall, type TraceExecutorRun, type TraceInspectionTarget, type TraceMetrics, type TraceStage } from '../traceProjection';
import styles from './ExecutionTrace.module.css';

interface ExecutionTraceProps {
  trace: SandboxTraceState;
  isRunning: boolean;
  onSelectTarget?: (target: TraceInspectionTarget) => void;
}

const formatDuration = (ms: number | undefined): string => {
  if (!ms) return '0 с';
  return `${Math.max(1, Math.round(ms / 1000))} с`;
};

function StatusBadge({ status }: { status: string }) {
  const normalized = status === 'completed' ? 'complete' : status === 'failed' ? 'fail' : status;
  return <span className={`${styles.status} ${styles[`status-${normalized}`] ?? ''}`}>{normalized}</span>;
}

function statusClass(status: string): string {
  if (status === 'completed' || status === 'complete') return styles.executorComplete;
  if (status === 'failed' || status === 'fail' || status === 'error') return styles.executorFailed;
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

function CallCard({ call, executor, stage, onSelect }: { call: TraceCall; executor: TraceExecutorRun; stage: TraceStage; onSelect?: (target: TraceInspectionTarget) => void }) {
  const typeLabel = {
    llm: 'LLM',
    tool: 'TOOL',
    clarify: 'УТОЧНЕНИЕ',
    confirm: 'ПОДТВЕРЖДЕНИЕ',
    error: 'ОШИБКА',
  }[call.kind];
  const statusLabel = call.kind === 'error'
    ? 'Ошибка'
    : call.response
      ? (call.kind === 'llm' ? 'Ответ' : call.kind === 'tool' ? 'Результат' : 'Ответ получен')
      : call.kind === 'clarify' ? 'Ожидает ответ' : call.kind === 'confirm' ? 'Ожидает решения' : 'Выполняется';
  return (
    <div className={styles.callWrap}>
      <button type="button" className={`${styles.call} ${styles[`call-${call.kind}`]}`} onClick={() => onSelect?.(call.kind === 'error' ? { kind: 'error', key: call.entity.key, call, executor, stage } : { kind: 'call', key: call.entity.key, call, executor, stage })}>
        <span className={styles.callType}>{typeLabel}</span>
        <span className={styles.callTitle}>{call.title}</span>
        <span className={`${styles.callStatus} ${call.kind === 'error' ? styles.callStatusError : call.response ? styles.callStatusComplete : styles.callStatusRunning}`}>{statusLabel}</span>
      </button>
    </div>
  );
}

function ExecutorRunCard({ executor, stage, onSelect }: { executor: TraceExecutorRun; stage: TraceStage; onSelect?: (target: TraceInspectionTarget) => void }) {
  const [expanded, setExpanded] = useState(false);
  const isTerminal = ['completed', 'complete', 'failed', 'fail', 'error'].includes(executor.entity.status);
  return (
    <article className={`${styles.executor} ${statusClass(executor.entity.status)}`}>
      <div className={styles.executorBody}>
        <button type="button" className={styles.executorLabel} onClick={() => onSelect?.({ kind: 'executor_run', key: executor.entity.key, executor, stage })}>
          <span className={styles.executorType}>{executor.executorType}</span>
          <span className={styles.executorName}>{executor.executorName}<small>{executor.executorSlug}</small></span>
          <span className={styles.executorStatus}><StatusBadge status={executor.entity.status} /></span>
        </button>
        {executor.calls.length > 0 && <button type="button" className={styles.executorExpand} aria-label="Показать вызовы исполнителя" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>⌄</button>}
      </div>
      <Metrics metrics={executor.metrics} hideElapsed={isTerminal} />
      {expanded && executor.calls.length > 0 && <div className={styles.callList}>{executor.calls.map((call) => <CallCard key={call.entity.key} call={call} executor={executor} stage={stage} onSelect={onSelect} />)}</div>}
    </article>
  );
}

function StageCard({ stage, onSelect }: { stage: TraceStage; onSelect?: (target: TraceInspectionTarget) => void }) {
  return (
    <div className={styles.stageRow}>
      <button type="button" className={styles.stageNumber} onClick={() => onSelect?.({ kind: 'step', key: stepFor(stage).key, step: stepFor(stage) })}>{stage.number || 1}</button>
      <div className={styles.stage}>
        <div className={styles.executorList}>{stage.executorRuns.map((executor) => <ExecutorRunCard key={executor.entity.key} executor={executor} stage={stage} onSelect={onSelect} />)}</div>
      </div>
    </div>
  );
}

export function ExecutionTrace({ trace, isRunning, onSelectTarget }: ExecutionTraceProps) {
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const stages = useMemo(() => projectTraceStages(trace), [trace]);
  useEffect(() => {
    if (!isRunning) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isRunning]);
  if (stages.length === 0) return null;
  return (
    <section className={styles.trace}>
      <button type="button" className={styles.summary} onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
        <span className={styles.summaryTitle}>Трейс выполнения ({formatDuration(traceElapsedMs(trace, now))})</span>
        {isRunning && <span className={styles.running}>выполняется</span>}
        <span className={`${styles.chevron} ${expanded ? styles.chevronOpen : ''}`}>⌄</span>
      </button>
      {expanded && <div className={styles.iterations}>{stages.map((stage) => (
        <article key={stage.entity.key} className={`${styles.iteration} ${styles[`iteration-${stage.iterationType}`] ?? ''}`}>
          <header className={styles.iterationHeader}>
            <button type="button" className={styles.iterationType} onClick={() => onSelectTarget?.({ kind: 'iteration', key: stage.entity.key, stage })}>
              {stage.label}
            </button>
            <span className={styles.iterationTask}>{stage.task}</span>
            <StatusBadge status={stage.entity.status} />
          </header>
          <div className={styles.iterationBody}><StageCard stage={stage} onSelect={onSelectTarget} /></div>
        </article>
      ))}</div>}
    </section>
  );
}
