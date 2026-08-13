import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { RuntimeJournalEvent } from '../../../types';

const asFacts = (events: RuntimeJournalEvent[]): Array<Record<string, unknown>> => {
  const payload = [...events].reverse().find((event) => event.event_type === 'memory_facts_result')?.payload;
  return Array.isArray(payload?.facts) ? payload.facts.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
};

export function FactsViewer({ events }: { events: RuntimeJournalEvent[] }) {
  const facts = asFacts(events);
  if (!facts.length) return <InspectorNotice tone="neutral" message="Факты на этом шаге не были извлечены или не прошли проверку." />;
  return <div>{facts.map((fact, index) => <InspectorFieldGroup key={`${String(fact.subject ?? '')}:${index}`}>
    <InspectorFieldRow label="Scope"><InspectorScalar value={String(fact.scope ?? '—')} /></InspectorFieldRow>
    <InspectorFieldRow label="Свойство"><InspectorScalar value={String(fact.subject ?? '—')} /></InspectorFieldRow>
    <InspectorFieldRow label="Значение"><InspectorScalar value={String(fact.value ?? '—')} /></InspectorFieldRow>
    {fact.status ? <InspectorFieldRow label="Статус"><InspectorStatus label={String(fact.status)} tone={fact.status === 'confirmed' ? 'success' : 'warn'} /></InspectorFieldRow> : null}
    {fact.support_count !== undefined ? <InspectorFieldRow label="Подтверждения"><InspectorScalar value={fact.support_count as number} /></InspectorFieldRow> : null}
    {fact.evidence_source_ids ? <InspectorFieldRow label="Источники"><InspectorJsonBlock value={fact.evidence_source_ids} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>)}</div>;
}
