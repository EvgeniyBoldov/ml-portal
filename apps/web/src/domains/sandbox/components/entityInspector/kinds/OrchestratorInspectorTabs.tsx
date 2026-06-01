import { InspectorTabs, InspectorFieldGroup, InspectorFieldRow } from '@/shared/ui/Inspector';
import { isOrchestratorData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab, SpendTab } from '../shared';

export function OrchestratorInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isOrchestratorData(entity.data) ? entity.data : null;
  const isPhase = entity.kind === 'phase' && entity.data.kind === 'phase';
  const tabs = isPhase
    ? [
      { key: 'info', label: 'Инфо' },
      { key: 'spend', label: 'Расход' },
      { key: 'raw', label: 'RAW' },
    ]
    : [
      { key: 'info', label: 'Инфо' },
      { key: 'overview', label: 'Обзор' },
      { key: 'budgets', label: 'Бюджет' },
      { key: 'raw', label: 'RAW' },
    ];

  return (
    <InspectorTabs
      entityId={entity.id}
      tabs={tabs}
      render={(tab) => {
        if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
        if (tab === 'spend') return <SpendTab entity={entity} />;
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
