import { InspectorTabs } from '@/shared/ui/Inspector';
import { isToolData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';
import { InspectorJsonBlock } from '@/shared/ui/Inspector';

export function ToolInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isToolData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'input', label: 'Input' }, { key: 'output', label: 'Output' }, { key: 'budgets', label: 'Budgets' }, { key: 'errors', label: 'Errors' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return (
      <>
        <InfoTab entity={entity} steps={steps} />
        <InspectorJsonBlock value={{ calledByAgentSlug: data?.calledByAgentSlug, calledByAgentRunId: data?.calledByAgentRunId }} />
      </>
    );
    if (tab === 'input') return <InspectorJsonBlock value={data?.arguments ?? '—'} />;
    if (tab === 'output') return <InspectorJsonBlock value={data?.result?.data ?? { success: data?.result?.success ?? false }} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    if (tab === 'errors') return <InspectorJsonBlock value={{ error: data?.result?.error, retries: data?.retries ?? [] }} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
