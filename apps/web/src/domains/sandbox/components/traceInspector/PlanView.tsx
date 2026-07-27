import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorTextBlock } from '@/shared/ui/Inspector';
import { projectPlan, type PlanTaskViewModel } from '../../planInspection';
import styles from './PlanView.module.css';

function statusTone(status?: string): 'neutral' | 'success' | 'warn' | 'danger' | 'info' {
  if (status === 'Готово') return 'success';
  if (status === 'Ошибка' || status === 'Невыполнима') return 'danger';
  if (status?.startsWith('Ожидает')) return 'warn';
  return 'info';
}

function TaskCard({ task }: { task: PlanTaskViewModel }) {
  return <article className={styles.task}>
    <div className={styles.taskHeader}><span className={styles.taskTitle}>{task.title}</span>{task.status ? <Badge tone={statusTone(task.status)} size="small">{task.status}</Badge> : null}</div>
    {task.objective ? <div className={styles.taskObjective}>{task.objective}</div> : null}
    <div className={styles.meta}>{task.executor ? <span>Исполнитель: {task.executor}</span> : <span>Исполнитель не назначен</span>}{task.dependencies.map((dependency) => <span key={dependency}>После: {dependency}</span>)}</div>
    {task.expectedOutputs.length ? <div className={styles.outputs}>Ожидаемый результат: {task.expectedOutputs.join(', ')}</div> : null}
    {task.inputs && typeof task.inputs === 'object' && Object.keys(task.inputs as Record<string, unknown>).length ? <InspectorJsonBlock value={task.inputs} /> : null}
  </article>;
}

export function HumanPlanView({ plan }: { plan: unknown }) {
  const value = projectPlan(plan);
  return <div className={styles.summary}>
    <InspectorFieldGroup>
      {value.decision ? <InspectorFieldRow label="Действие">{value.decision}</InspectorFieldRow> : null}
      {value.revision !== undefined ? <InspectorFieldRow label="Ревизия">{value.revision}</InspectorFieldRow> : null}
      {value.trigger ? <InspectorFieldRow label="Причина">{value.trigger}</InspectorFieldRow> : null}
      {value.goal ? <InspectorFieldRow label="Цель"><InspectorTextBlock text={value.goal} /></InspectorFieldRow> : null}
      {value.rationale ? <InspectorFieldRow label="Обоснование"><InspectorTextBlock text={value.rationale} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    <div className={styles.taskList}>{value.tasks.length ? value.tasks.map((task, index) => <TaskCard key={`${task.title}:${index}`} task={task} />) : <InspectorFieldGroup><InspectorFieldRow label="Задачи">План не содержит задач</InspectorFieldRow></InspectorFieldGroup>}</div>
    {value.removedTasks.length ? <div className={styles.removed}>Исключено из плана: {value.removedTasks.join(', ')}</div> : null}
  </div>;
}
