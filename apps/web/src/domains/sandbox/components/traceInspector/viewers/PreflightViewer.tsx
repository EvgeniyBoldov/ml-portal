import Badge from '@/shared/ui/Badge';
import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorScalar } from '@/shared/ui/Inspector';
import type { TracePreflight } from '../../../traceProjection';

const statusTone = (status: string): 'neutral' | 'success' | 'warn' | 'danger' => {
  if (['completed', 'ok', 'ready'].includes(status)) return 'success';
  if (['failed', 'error'].includes(status)) return 'danger';
  if (status === 'partial') return 'warn';
  return 'neutral';
};

const missingLabel = (items: string[]): string => items.length ? items.join(', ') : 'Нет';

/** Typed availability summary prepared by the trace projection for one executor. */
export function PreflightViewer({ preflight }: { preflight?: TracePreflight }) {
  if (!preflight) return <InspectorNotice tone="neutral" message="Preflight-снимок для этого исполнителя не записан в журнал." />;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><Badge size="small" tone={statusTone(preflight.status)}>{preflight.status}</Badge></InspectorFieldRow>
    {preflight.mode ? <InspectorFieldRow label="Режим"><InspectorScalar value={preflight.mode} /></InspectorFieldRow> : null}
    {preflight.durationMs !== undefined ? <InspectorFieldRow label="Длительность"><InspectorScalar value={`${preflight.durationMs} мс`} /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Недостающие инструменты"><InspectorScalar value={missingLabel(preflight.missing.tools)} /></InspectorFieldRow>
    <InspectorFieldRow label="Недоступные коллекции"><InspectorScalar value={missingLabel(preflight.missing.collections)} /></InspectorFieldRow>
    <InspectorFieldRow label="Недостающие учётные данные"><InspectorScalar value={missingLabel(preflight.missing.credentials)} /></InspectorFieldRow>
    {preflight.operationsCount !== undefined ? <InspectorFieldRow label="Доступные операции"><InspectorScalar value={preflight.operationsCount} /></InspectorFieldRow> : null}
    {preflight.dataInstancesCount !== undefined ? <InspectorFieldRow label="Доступные источники"><InspectorScalar value={preflight.dataInstancesCount} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
