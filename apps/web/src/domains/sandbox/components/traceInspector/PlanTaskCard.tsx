import Badge from '@/shared/ui/Badge';
import { InspectorJsonBlock } from '@/shared/ui/Inspector';
import type { PlanTaskViewModel } from '../../planInspection';
import styles from './PlanTaskCard.module.css';

function statusTone(status?: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (status === 'Готово') return 'success';
  if (status === 'Ошибка' || status === 'Невыполнима') return 'danger';
  if (status?.startsWith('Ожидает')) return 'warn';
  return 'info';
}

function TaskMeta({ task }: { task: PlanTaskViewModel }) {
  return <div className={styles.meta}>
    <span>{task.executor ? `Исполнитель: ${task.executor}` : 'Исполнитель не назначен'}</span>
    {task.dependencies.map((dependency) => <span key={dependency}>После: {dependency}</span>)}
  </div>;
}

function TaskDetails({ task }: { task: PlanTaskViewModel }) {
  return <div className={styles.details}>
    {task.intent ? <div><span className={styles.label}>Intent</span><span>{task.intent}</span></div> : null}
    {task.instructions ? <div><span className={styles.label}>Инструкции</span><span className={styles.instructions}>{task.instructions}</span></div> : null}
    {task.expectedOutputs.length ? <div><span className={styles.label}>Ожидаемый результат</span><span>{task.expectedOutputs.join(', ')}</span></div> : null}
    {task.inputs && typeof task.inputs === 'object' && Object.keys(task.inputs as Record<string, unknown>).length ? <InspectorJsonBlock value={task.inputs} /> : null}
  </div>;
}

function TaskHeader({ task }: { task: PlanTaskViewModel }) {
  return <div className={styles.header}>
    <div className={styles.titleBlock}>
      <span className={styles.taskId}>{task.taskId}</span>
      <span className={styles.title}>{task.title}</span>
    </div>
    {task.status ? <Badge tone={statusTone(task.status)} size="small">{task.status}</Badge> : null}
  </div>;
}

export function PlanTaskCard({ task, variant = 'expanded' }: { task: PlanTaskViewModel; variant?: 'compact' | 'expanded' }) {
  if (variant === 'compact') {
    return <details className={`${styles.task} ${styles.compact}`}>
      <summary><TaskHeader task={task} /><div className={styles.objective}>{task.objective ?? task.instructions ?? task.intent}</div><TaskMeta task={task} /></summary>
      <TaskDetails task={task} />
    </details>;
  }

  return <article className={styles.task}>
    <TaskHeader task={task} />
    {task.objective ? <div className={styles.objective}>{task.objective}</div> : null}
    <TaskMeta task={task} />
    <TaskDetails task={task} />
  </article>;
}
