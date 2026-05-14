import { InspectorTabs } from '@/shared/ui/Inspector';
import { isRunData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';
import { InspectorFieldGroup, InspectorFieldRow } from '@/shared/ui/Inspector';

export function RunInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isRunData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'response', label: 'Response' }, { key: 'budgets', label: 'Budgets' }, { key: 'raw', label: 'Raw' }];

  return (
    <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
      if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
      if (tab === 'response') {
        return (
          <InspectorFieldGroup>
            <InspectorFieldRow label="Request">{data?.userRequest ?? '—'}</InspectorFieldRow>
            <InspectorFieldRow label="Agent">{data?.agentSlug ?? '—'}</InspectorFieldRow>
            {data?.finalContent ? <InspectorFieldRow label="Response">{data.finalContent}</InspectorFieldRow> : null}
            {data?.finalError ? <InspectorFieldRow label="Error">{data.finalError}</InspectorFieldRow> : null}
          </InspectorFieldGroup>
        );
      }
      if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
      return <RawTab value={entity.data} entity={entity} steps={steps} />;
    }} />
  );
}
