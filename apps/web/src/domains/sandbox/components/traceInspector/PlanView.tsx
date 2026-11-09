import {
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorNotice,
  InspectorTextBlock,
} from '@/shared/ui/Inspector';
import type {
  PlanCheckpointViewModel,
  PlanViewModel,
} from '@domains/sandbox/planInspection';
import Badge from '@/shared/ui/Badge';
import { PlanTaskCard } from './PlanTaskCard';
import styles from './PlanView.module.css';

function PlanCheckpoint({
  checkpoint,
}: {
  checkpoint: PlanCheckpointViewModel;
}) {
  const label = (value?: string) =>
    value === 'planner'
      ? 'Планировщик'
      : value === 'synthesis'
        ? 'Синтез ответа'
        : value || 'Не определено';
  return (
    <article
      className={styles.checkpoint}
      aria-label={`Контрольная точка итерации ${checkpoint.iteration}`}
    >
      <div className={styles.checkpointHeader}>
        <strong>Контрольная точка · итерация {checkpoint.iteration}</strong>
        <Badge tone={checkpoint.decided ? 'success' : 'neutral'} size="small">
          {checkpoint.decided ? 'Решена' : 'Ожидает'}
        </Badge>
      </div>
      <div>Запланировано: {label(checkpoint.declaredNext)}</div>
      {checkpoint.decided ? (
        <div>Решение: {label(checkpoint.effectiveNext)}</div>
      ) : null}
      {checkpoint.reason && checkpoint.reason !== 'terminal' ? (
        <div>
          Причина:{' '}
          {checkpoint.reason === 'task_failure'
            ? 'ошибка задачи'
            : checkpoint.reason}
        </div>
      ) : null}
    </article>
  );
}

export function HumanPlanView({ plan }: { plan?: PlanViewModel }) {
  if (!plan)
    return (
      <InspectorNotice
        tone="neutral"
        message="План для этого этапа не записан в журнал."
      />
    );
  const value = plan;
  return (
    <div className={styles.summary}>
      <InspectorFieldGroup>
        {value.terminal ? (
          <InspectorFieldRow label="Terminal">
            {value.terminal}
          </InspectorFieldRow>
        ) : null}
        {value.iteration !== undefined ? (
          <InspectorFieldRow label="Итерация">
            {value.iteration}
          </InspectorFieldRow>
        ) : null}
        {value.trigger ? (
          <InspectorFieldRow label="Причина">{value.trigger}</InspectorFieldRow>
        ) : null}
        {value.goal ? (
          <InspectorFieldRow label="Цель">
            <InspectorTextBlock text={value.goal} />
          </InspectorFieldRow>
        ) : null}
      </InspectorFieldGroup>
      {value.historyIncomplete ? (
        <InspectorNotice
          tone="warn"
          message="История плана неполная: некоторые предыдущие решения или задачи отсутствуют в трассе."
        />
      ) : null}
      <div className={styles.taskList}>
        {value.entries ? (
          value.entries.length ? (
            value.entries.map(entry =>
              entry.kind === 'task' ? (
                <PlanTaskCard
                  key={`task:${entry.task.taskId}`}
                  task={entry.task}
                />
              ) : (
                <PlanCheckpoint
                  key={`checkpoint:${entry.checkpoint.id}`}
                  checkpoint={entry.checkpoint}
                />
              )
            )
          ) : (
            <InspectorFieldGroup>
              <InspectorFieldRow label="Изменения">
                Новых задач и решений нет
              </InspectorFieldRow>
            </InspectorFieldGroup>
          )
        ) : value.tasks.length ? (
          value.tasks.map(task => (
            <PlanTaskCard key={task.taskId} task={task} />
          ))
        ) : (
          <InspectorFieldGroup>
            <InspectorFieldRow label="Задачи">
              План не содержит задач
            </InspectorFieldRow>
          </InspectorFieldGroup>
        )}
      </div>
    </div>
  );
}
