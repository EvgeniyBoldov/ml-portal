import { InspectorFieldGroup, InspectorFieldRow, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { TraceCheckpointDecision } from '../../../traceProjection';

const destinationLabel = (value: string | undefined): string => {
  if (value === 'planner') return 'Планирование';
  if (value === 'synthesis') return 'Синтез ответа';
  return value || 'Не задано';
};

const reasonLabel = (value: string | undefined): string => {
  if (value === 'task_failure') return 'Предыдущая задача завершилась ошибкой';
  if (value === 'all_tasks_completed') return 'Все задачи завершены';
  if (value === 'planner_terminal') return 'Планировщик завершил план';
  return value || 'Причина не записана';
};

export function CheckpointViewer({ decision }: { decision: TraceCheckpointDecision | undefined }) {
  if (!decision) return <InspectorFieldGroup><InspectorFieldRow label="Решение">Нет данных</InspectorFieldRow></InspectorFieldGroup>;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Состояние">
      <InspectorStatus label={decision.decided ? 'Решение принято' : 'Ожидает решения'} tone={decision.decided ? 'success' : 'warn'} />
    </InspectorFieldRow>
    {decision.declaredNext ? <InspectorFieldRow label="Планировщик предложил"><InspectorScalar value={destinationLabel(decision.declaredNext)} /></InspectorFieldRow> : null}
    {decision.decided ? <InspectorFieldRow label="Фактический переход"><InspectorScalar value={destinationLabel(decision.effectiveNext)} /></InspectorFieldRow> : null}
    {decision.reason ? <InspectorFieldRow label="Причина"><InspectorScalar value={reasonLabel(decision.reason)} /></InspectorFieldRow> : null}
    {decision.iterationId ? <InspectorFieldRow label="Итерация плана"><InspectorScalar value={decision.iterationId} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
