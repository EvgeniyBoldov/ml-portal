import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { TraceMemoryContext } from '../../../traceProjection';

export function MemoryContextViewer({ context }: { context?: TraceMemoryContext }) {
  if (!context) return <InspectorNotice tone="neutral" message="Подготовленный memory context не записан в журнал." />;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Статус"><InspectorStatus label={context.fallback ? 'Fallback без памяти' : 'Подготовлен'} tone={context.fallback ? 'warn' : 'success'} /></InspectorFieldRow>
    <InspectorFieldRow label="Выбрано фактов"><InspectorScalar value={context.selectedFacts} /></InspectorFieldRow>
    <InspectorFieldRow label="Выбрано проектов"><InspectorScalar value={context.selectedProjects} /></InspectorFieldRow>
    {context.context.length ? <InspectorFieldRow label="Контекст планера"><InspectorJsonBlock value={context.context} /></InspectorFieldRow> : null}
    {context.ambiguities.length ? <InspectorFieldRow label="Неоднозначности"><InspectorJsonBlock value={context.ambiguities} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
