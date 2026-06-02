import { InspectorTabs } from '@/shared/ui/Inspector';
import { isErrorData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { InfoTab, RawTab, SnapshotJsonField } from '../shared';
import { InspectorFieldGroup } from '@/shared/ui/Inspector';

export function ErrorInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isErrorData(entity.data) ? entity.data : null;
  const tabs = [
    { key: 'info', label: 'Инфо' },
    { key: 'summary', label: 'Сводка' },
    { key: 'context', label: 'Контекст' },
    { key: 'raw', label: 'RAW' },
  ];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'summary') return <InspectorFieldGroup><SnapshotJsonField label="Сводка" value={{ code: data?.code, userMessage: data?.userMessage, operatorMessage: data?.operatorMessage }} /></InspectorFieldGroup>;
    if (tab === 'context') return <InspectorFieldGroup><SnapshotJsonField label="Контекст" value={data?.debug ?? '—'} /></InspectorFieldGroup>;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
