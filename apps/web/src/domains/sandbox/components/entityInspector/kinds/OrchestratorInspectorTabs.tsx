import { InspectorTabs, InspectorFieldGroup, InspectorFieldRow } from '@/shared/ui/Inspector';
import { isOrchestratorData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function OrchestratorInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isOrchestratorData(entity.data) ? entity.data : null;
  const tabs = [
    { key: 'info', label: 'Info' },
    { key: 'overview', label: 'Overview' },
    { key: 'budgets', label: 'Budgets' },
    { key: 'raw', label: 'Raw' },
  ];

  return (
    <InspectorTabs
      entityId={entity.id}
      tabs={tabs}
      render={(tab) => {
        if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
        if (tab === 'overview') {
          return (
            <InspectorFieldGroup>
              <InspectorFieldRow label="Slug">{data?.slug ?? '—'}</InspectorFieldRow>
              <InspectorFieldRow label="Role">{data?.role ?? '—'}</InspectorFieldRow>
              <InspectorFieldRow label="Intent">{data?.intent ?? '—'}</InspectorFieldRow>
            </InspectorFieldGroup>
          );
        }
        if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
        return <RawTab value={entity.data} entity={entity} steps={steps} />;
      }}
    />
  );
}
