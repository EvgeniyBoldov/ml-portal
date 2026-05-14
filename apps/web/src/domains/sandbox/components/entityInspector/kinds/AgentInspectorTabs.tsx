import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorTabs, InspectorTextBlock } from '@/shared/ui/Inspector';
import { isAgentData, isLLMData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function AgentInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isAgentData(entity.data) ? entity.data : null;
  const llmChild = entity.children?.find((c) => c.kind === 'llm');
  const llmData = llmChild && isLLMData(llmChild.data) ? llmChild.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'prompt', label: 'Prompt' }, { key: 'response', label: 'Response' }, { key: 'budgets', label: 'Budgets' }, { key: 'rbac', label: 'RBAC' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'prompt') {
      if (llmData?.prompt?.isBriefMode) {
        return <InspectorNotice tone="info" title="Brief Logging" message="Messages не сохранены" />;
      }
      return <InspectorJsonBlock value={llmData?.prompt?.messages ?? llmData?.prompt?.systemPrompt ?? data?.prompt?.systemPrompt ?? '—'} />;
    }
    if (tab === 'response') return <InspectorTextBlock text={llmData?.response?.content ?? llmData?.response?.rawResponse ?? '—'} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    if (tab === 'rbac') return <InspectorFieldGroup><InspectorFieldRow label="Slug">{data?.slug ?? '—'}</InspectorFieldRow><InspectorFieldRow label="Version">{data?.versionLabel ?? data?.versionId ?? '—'}</InspectorFieldRow></InspectorFieldGroup>;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
