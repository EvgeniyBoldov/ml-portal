import Badge from '@/shared/ui/Badge';
import { InspectorJsonBlock } from '@/shared/ui/Inspector';
import type { PlanTaskViewModel } from '@domains/sandbox/planInspection';
import styles from './PlanTaskCard.module.css';

function statusTone(
  status?: string
): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (status === 'Готово') return 'success';
  if (status === 'Ошибка' || status === 'Невыполнима') return 'danger';
  if (status?.startsWith('Ожидает')) return 'warn';
  return 'info';
}

function TaskMeta({ task }: { task: PlanTaskViewModel }) {
  return (
    <div className={styles.meta}>
      {task.iterationNumber !== undefined ? (
        <span>Итерация: {task.iterationNumber}</span>
      ) : null}
      <span>
        {task.executor
          ? `Исполнитель: ${task.executor}`
          : 'Исполнитель не назначен'}
      </span>
      {task.dependencies.map(dependency => (
        <span key={dependency}>После: {dependency}</span>
      ))}
    </div>
  );
}

function TaskDetails({ task }: { task: PlanTaskViewModel }) {
  return (
    <div className={styles.details}>
      {task.intent && task.intent !== task.title ? (
        <div>
          <span className={styles.label}>Intent</span>
          <span>{task.intent}</span>
        </div>
      ) : null}
      {task.instructions ? (
        <div>
          <span className={styles.label}>Инструкции</span>
          <span className={styles.instructions}>{task.instructions}</span>
        </div>
      ) : null}
      {task.expectedOutputs.length ? (
        <div>
          <span className={styles.label}>Ожидаемый результат</span>
          <span>{task.expectedOutputs.join(', ')}</span>
        </div>
      ) : null}
      {task.inputs &&
      typeof task.inputs === 'object' &&
      Object.keys(task.inputs as Record<string, unknown>).length ? (
        <InspectorJsonBlock value={task.inputs} />
      ) : null}
    </div>
  );
}

function TaskHeader({ task }: { task: PlanTaskViewModel }) {
  const changeLabel = task.change
    ? (
        {
          new: 'Новая',
          continuation: 'Продолжение',
          superseded: 'Продолжена новой задачей',
          excluded: 'Исключена',
          cancelled: 'Отменена',
          partial: 'Принят частичный результат',
          unresolved: 'Оставлена нерешённой',
        } as const
      )[task.change]
    : undefined;
  const changeTone =
    task.change === 'new'
      ? 'success'
      : task.change === 'continuation' ||
          task.change === 'partial' ||
          task.change === 'unresolved'
        ? 'warn'
        : 'neutral';
  return (
    <div className={styles.header}>
      <div className={styles.titleBlock}>
        <span className={styles.taskId}>{task.taskId}</span>
        <span className={styles.title}>{task.title}</span>
      </div>
      <div className={styles.badges}>
        {changeLabel ? (
          <Badge tone={changeTone} size="small">
            {changeLabel}
          </Badge>
        ) : null}
        {task.status && task.status !== changeLabel ? (
          <Badge tone={statusTone(task.status)} size="small">
            {task.status}
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

function TaskChange({ task }: { task: PlanTaskViewModel }) {
  if (!task.relatedTaskIds?.length && !task.changeReason) return null;
  return (
    <div className={styles.change}>
      {task.relatedTaskIds?.length ? (
        <span>
          {task.change === 'superseded' ? 'Продолжение: ' : 'Продолжает: '}
          {task.relatedTaskIds.join(', ')}
        </span>
      ) : null}
      {task.changeReason ? <span>{task.changeReason}</span> : null}
    </div>
  );
}

export function PlanTaskCard({
  task,
  variant = 'expanded',
}: {
  task: PlanTaskViewModel;
  variant?: 'compact' | 'expanded';
}) {
  if (variant === 'compact') {
    return (
      <details
        className={`${styles.task} ${styles.compact} ${task.inactive ? styles.inactive : ''} ${task.change === 'new' ? styles.new : task.change === 'continuation' ? styles.continuation : ''}`}
      >
        <summary>
          <TaskHeader task={task} />
          <div className={styles.objective}>
            {task.objective ?? task.instructions ?? task.intent}
          </div>
          <TaskMeta task={task} />
          <TaskChange task={task} />
        </summary>
        <TaskDetails task={task} />
      </details>
    );
  }

  return (
    <article
      className={`${styles.task} ${task.inactive ? styles.inactive : ''} ${task.change === 'new' ? styles.new : task.change === 'continuation' ? styles.continuation : ''}`}
    >
      <TaskHeader task={task} />
      {task.objective ? (
        <div className={styles.objective}>{task.objective}</div>
      ) : null}
      <TaskMeta task={task} />
      <TaskChange task={task} />
      <TaskDetails task={task} />
    </article>
  );
}
