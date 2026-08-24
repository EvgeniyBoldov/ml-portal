import { InspectorFieldGroup, InspectorFieldRow, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceMemoryContext, TraceMemoryContextItem } from '../../../traceProjection';
import { InspectorEmptyState, InspectorSection, InspectorStack } from '../InspectorPrimitives';

function Item({ item }: { item: TraceMemoryContextItem }) {
  if (item.type === 'fact') return <InspectorFieldGroup><InspectorFieldRow label="Тип"><InspectorScalar value="Факт" /></InspectorFieldRow><InspectorFieldRow label="Область"><InspectorScalar value={item.scope} /></InspectorFieldRow><InspectorFieldRow label="Свойство"><InspectorScalar value={item.subject} /></InspectorFieldRow><InspectorFieldRow label="Значение"><InspectorScalar value={item.value} /></InspectorFieldRow></InspectorFieldGroup>;
  if (item.type === 'project') return <InspectorFieldGroup><InspectorFieldRow label="Тип"><InspectorScalar value="Проект" /></InspectorFieldRow><InspectorFieldRow label="Ключ"><InspectorScalar value={item.key} /></InspectorFieldRow><InspectorFieldRow label="Название"><InspectorScalar value={item.name} /></InspectorFieldRow>{item.matchedAliases.length ? <InspectorFieldRow label="Совпавшие алиасы"><InspectorTextBlock text={item.matchedAliases.join(', ')} /></InspectorFieldRow> : null}</InspectorFieldGroup>;
  return <InspectorFieldGroup><InspectorFieldRow label="Тип"><InspectorScalar value="Термин" /></InspectorFieldRow><InspectorFieldRow label="Область"><InspectorScalar value={item.scope} /></InspectorFieldRow><InspectorFieldRow label="Термин"><InspectorScalar value={item.term} /></InspectorFieldRow><InspectorFieldRow label="Описание"><InspectorTextBlock text={item.description} /></InspectorFieldRow>{item.aliases.length ? <InspectorFieldRow label="Алиасы"><InspectorTextBlock text={item.aliases.join(', ')} /></InspectorFieldRow> : null}</InspectorFieldGroup>;
}

export function MemoryContextViewer({ context }: { context?: TraceMemoryContext }) {
  if (!context) return <InspectorEmptyState message="Подготовленный memory context не записан в журнал." />;
  return <InspectorStack>
    <InspectorFieldGroup>
      <InspectorFieldRow label="Статус"><InspectorStatus label={context.fallback ? 'Fallback без памяти' : 'Подготовлен'} tone={context.fallback ? 'warn' : 'success'} /></InspectorFieldRow>
      <InspectorFieldRow label="Выбрано фактов"><InspectorScalar value={context.selectedFacts} /></InspectorFieldRow>
      <InspectorFieldRow label="Выбрано проектов"><InspectorScalar value={context.selectedProjects} /></InspectorFieldRow>
    </InspectorFieldGroup>
    {context.context.length ? <InspectorSection title="Контекст"> <InspectorStack>{context.context.map((item, index) => <Item key={`${item.type}:${index}`} item={item} />)}</InspectorStack></InspectorSection> : null}
    {context.ambiguities.length ? <InspectorSection title="Неоднозначности"><InspectorTextBlock text={context.ambiguities.join('\n')} /></InspectorSection> : null}
  </InspectorStack>;
}
