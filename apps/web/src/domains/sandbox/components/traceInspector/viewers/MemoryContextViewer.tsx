import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { RuntimeJournalEvent } from '../../../types';

export function MemoryContextViewer({ events }: { events: RuntimeJournalEvent[] }) {
  const payload = [...events].reverse().find((event) => event.event_type === 'status' && event.payload.stage === 'memory_context_prepared')?.payload;
  if (!payload) return <InspectorNotice tone="neutral" message="Подготовленный memory context не записан в журнал." />;
  const ambiguities = Array.isArray(payload.ambiguities) ? payload.ambiguities : [];
  const context = Array.isArray(payload.memory_context) ? payload.memory_context : [];
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={payload.fallback === true ? 'Fallback без памяти' : 'Подготовлен'} tone={payload.fallback === true ? 'warn' : 'success'} /></InspectorFieldRow>
    <InspectorFieldRow label="Выбрано фактов"><InspectorScalar value={typeof payload.selected_facts === 'number' ? payload.selected_facts : 0} /></InspectorFieldRow>
    <InspectorFieldRow label="Выбрано проектов"><InspectorScalar value={typeof payload.selected_projects === 'number' ? payload.selected_projects : 0} /></InspectorFieldRow>
    {context.length ? <InspectorFieldRow label="Контекст планера"><InspectorJsonBlock value={context} /></InspectorFieldRow> : null}
    {ambiguities.length ? <InspectorFieldRow label="Неоднозначности"><InspectorJsonBlock value={ambiguities} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
