import { InspectorFieldGroup, InspectorFieldRow, InspectorTextBlock } from '@/shared/ui/Inspector';
import { projectPlan } from '../../planInspection';
import { PlanTaskCard } from './PlanTaskCard';
import styles from './PlanView.module.css';

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
    <div className={styles.taskList}>{value.tasks.length ? value.tasks.map((task) => <PlanTaskCard key={task.taskId} task={task} />) : <InspectorFieldGroup><InspectorFieldRow label="Задачи">План не содержит задач</InspectorFieldRow></InspectorFieldGroup>}</div>
    {value.removedTasks.length ? <div className={styles.removed}>Исключено из плана: {value.removedTasks.join(', ')}</div> : null}
  </div>;
}
