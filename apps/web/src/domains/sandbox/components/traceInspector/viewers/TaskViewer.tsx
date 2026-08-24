import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { PlanTaskViewModel } from '../../../planInspection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const list = (value: string[]): string => value.join('\n');

export function TaskViewer({ task }: { task?: PlanTaskViewModel }) {
  if (!task) return <InspectorEmptyState message="Описание задачи для этого исполнителя не записано в журнал." />;
  const goal = task.objective ?? task.instructions ?? task.intent;
  return <InspectorFieldGroup>
    {goal ? <InspectorFieldRow label="Цель"><InspectorTextBlock text={goal} /></InspectorFieldRow> : null}
    {task.intent ? <InspectorFieldRow label="Назначение"><InspectorScalar value={task.intent} /></InspectorFieldRow> : null}
    {task.instructions && task.instructions !== goal ? <InspectorFieldRow label="Инструкции"><InspectorTextBlock text={task.instructions} /></InspectorFieldRow> : null}
    {task.inputs !== undefined ? <InspectorFieldRow label="Входные данные"><InspectorJsonBlock value={task.inputs} /></InspectorFieldRow> : null}
    {task.dependencies.length ? <InspectorFieldRow label="Зависимости"><InspectorTextBlock text={list(task.dependencies)} /></InspectorFieldRow> : null}
    {task.expectedOutputs.length ? <InspectorFieldRow label="Ожидаемый результат"><InspectorTextBlock text={list(task.expectedOutputs)} /></InspectorFieldRow> : null}
    {task.status ? <InspectorFieldRow label="Статус задачи"><InspectorScalar value={task.status} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
