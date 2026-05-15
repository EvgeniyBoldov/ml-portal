import { InspectorTabs } from '@/shared/ui/Inspector';
import { isToolData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';
import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock } from '@/shared/ui/Inspector';

export function ToolInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isToolData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'input', label: 'Input' }, { key: 'output', label: 'Output' }, { key: 'budgets', label: 'Budgets' }, { key: 'errors', label: 'Errors' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return (
      <>
        <InfoTab entity={entity} steps={steps} />
        <InspectorFieldGroup>
          <InspectorFieldRow label="Tool"><code>{data?.toolSlug ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Call ID"><code>{data?.callId ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Called By Agent"><code>{data?.calledByAgentSlug ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Agent Run ID"><code>{data?.calledByAgentRunId ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="LLM Call ID"><code>{data?.llmCallId ?? '—'}</code></InspectorFieldRow>
        </InspectorFieldGroup>
      </>
    );
    if (tab === 'input') return <InspectorJsonBlock value={data?.arguments ?? '—'} />;
    if (tab === 'output') return <InspectorJsonBlock value={data?.result?.data ?? { success: data?.result?.success ?? false }} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    if (tab === 'errors') return <InspectorJsonBlock value={{ error: data?.result?.error, retries: data?.retries ?? [] }} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
