import { InspectorFieldGroup, InspectorNotice, InspectorTabs } from '@/shared/ui/Inspector';
import { isUnknownData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { InfoTab, SnapshotJsonField } from '../shared';

export function UnknownInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isUnknownData(entity.data) ? entity.data : null;
  const tabs = [
    { key: 'info', label: 'Инфо' },
    { key: 'raw', label: 'RAW' },
    { key: 'hint', label: 'Подсказка' },
  ];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'raw') {
      return (
        <InspectorFieldGroup>
          <SnapshotJsonField label="RAW" value={data?.raw ?? '—'} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'hint') return <InspectorNotice tone="warn" title="Новый тип события" message={data?.hint ?? 'Неизвестный тип события'} code={data?.rawType} />;
    return null;
  }} />;
}
