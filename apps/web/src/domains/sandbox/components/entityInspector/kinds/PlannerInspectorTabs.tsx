import { InspectorJsonBlock, InspectorTabs, InspectorTextBlock } from '@/shared/ui/Inspector';
import { isPlannerData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function PlannerInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isPlannerData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'decision', label: 'Decision' }, { key: 'rationale', label: 'Rationale' }, { key: 'budgets', label: 'Budgets' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'decision') return <InspectorJsonBlock value={{ kind: data?.stepKind, chosenAgent: data?.decision?.chosenAgentSlug }} />;
    if (tab === 'rationale') return <InspectorTextBlock text={data?.rationale ?? '—'} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
