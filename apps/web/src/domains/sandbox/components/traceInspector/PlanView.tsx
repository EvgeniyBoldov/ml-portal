import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { PlanViewModel } from '@domains/sandbox/planInspection';
import { PlanTaskCard } from './PlanTaskCard';
import styles from './PlanView.module.css';

export function HumanPlanView({ plan }: { plan?: PlanViewModel }) {
  if (!plan) return <InspectorNotice tone="neutral" message="План для этого этапа не записан в журнал." />;
  const value = plan;
  return <div className={styles.summary}>
    <InspectorFieldGroup>
      {value.terminal ? <InspectorFieldRow label="Terminal">{value.terminal}</InspectorFieldRow> : null}
      {value.iteration !== undefined ? <InspectorFieldRow label="Итерация">{value.iteration}</InspectorFieldRow> : null}
      {value.trigger ? <InspectorFieldRow label="Причина">{value.trigger}</InspectorFieldRow> : null}
      {value.goal ? <InspectorFieldRow label="Цель"><InspectorTextBlock text={value.goal} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    <div className={styles.taskList}>{value.tasks.length ? value.tasks.map((task) => <PlanTaskCard key={task.taskId} task={task} />) : <InspectorFieldGroup><InspectorFieldRow label="Задачи">План не содержит задач</InspectorFieldRow></InspectorFieldGroup>}</div>
  </div>;
}
