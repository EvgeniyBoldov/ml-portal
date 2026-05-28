import { InspectorFieldGroup, InspectorJsonBlock, InspectorNotice, InspectorTabs } from '@/shared/ui/Inspector';
import { isUnknownData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { InfoTab } from '../shared';

export function UnknownInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isUnknownData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'raw', label: 'Raw' }, { key: 'hint', label: 'Hint' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'raw') {
      return (
        <InspectorFieldGroup>
          <InspectorJsonBlock value={data?.raw ?? '—'} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'hint') return <InspectorNotice tone="warn" title="New Event Type" message={data?.hint ?? 'Unknown event type'} code={data?.rawType} />;
    return null;
  }} />;
}
