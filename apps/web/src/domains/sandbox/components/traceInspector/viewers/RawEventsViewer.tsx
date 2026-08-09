import { InspectorFieldGroup, InspectorFieldRow, InspectorReadonlyBlock } from '@/shared/ui/Inspector';

export type RawTraceEvent = { sequence: number; eventType: string; value: unknown };

export function RawEventsViewer({ events }: { events: RawTraceEvent[] }) {
  if (!events.length) return <InspectorFieldGroup><InspectorFieldRow label="RAW">Нет данных</InspectorFieldRow></InspectorFieldGroup>;
  return <InspectorFieldGroup>{events.map((event) => <InspectorFieldRow key={`${event.sequence}:${event.eventType}`} label={`#${event.sequence} · ${event.eventType}`}><InspectorReadonlyBlock value={event.value} /></InspectorFieldRow>)}</InspectorFieldGroup>;
}
