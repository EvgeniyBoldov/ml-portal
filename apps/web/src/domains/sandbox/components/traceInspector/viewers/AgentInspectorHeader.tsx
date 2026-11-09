import { InspectorStatus } from '@/shared/ui/Inspector';
import type { TraceExecutorRun } from '../../../traceProjection';
import { traceStatusTone } from '../../../traceStatus';
import styles from './AgentInspectorHeader.module.css';

const duration = (value: number): string => value >= 1000
  ? `${(value / 1000).toFixed(1)} с`
  : `${value} мс`;

export function AgentInspectorHeader({ executor }: { executor: TraceExecutorRun }) {
  const description = executor.accessSnapshot?.agentDescription;

  return <div className={styles.header}>
    <div className={styles.identity}>
      <strong className={styles.name}>{executor.executorName}</strong>
      {description ? <p className={styles.description}>{description}</p> : null}
    </div>
    <div className={styles.statusLine}>
      <InspectorStatus label={executor.info.statusLabel} tone={traceStatusTone(executor.info.status)} />
      {executor.info.durationMs !== undefined ? <span className={styles.duration}>Время исполнения: {duration(executor.info.durationMs)}</span> : null}
    </div>
  </div>;
}
