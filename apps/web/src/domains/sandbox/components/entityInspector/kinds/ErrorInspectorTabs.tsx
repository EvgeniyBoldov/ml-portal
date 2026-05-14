import { InspectorTabs } from '@/shared/ui/Inspector';
import { isErrorData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { InfoTab, RawTab } from '../shared';
import { InspectorJsonBlock } from '@/shared/ui/Inspector';

export function ErrorInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isErrorData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'summary', label: 'Summary' }, { key: 'context', label: 'Context' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'summary') return <InspectorJsonBlock value={{ code: data?.code, userMessage: data?.userMessage, operatorMessage: data?.operatorMessage }} />;
    if (tab === 'context') return <InspectorJsonBlock value={data?.debug ?? '—'} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
