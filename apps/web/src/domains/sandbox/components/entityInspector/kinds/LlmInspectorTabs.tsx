import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorTabs, InspectorTextBlock } from '@/shared/ui/Inspector';
import { isLLMData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function LlmInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isLLMData(entity.data) ? entity.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'prompt', label: 'Prompt' }, { key: 'response', label: 'Response' }, { key: 'budgets', label: 'Budgets' }, { key: 'raw', label: 'Raw' }];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return (
      <>
        <InfoTab entity={entity} steps={steps} />
        <InspectorFieldGroup>
          <InspectorFieldRow label="LLM Call ID"><code>{data?.llmCallId ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Purpose"><code>{data?.purpose ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Parent Type"><code>{data?.parentEntityType ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Parent ID"><code>{data?.parentEntityId ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Model"><code>{data?.params?.model ?? '—'}</code></InspectorFieldRow>
          <InspectorFieldRow label="Tokens In">{data?.tokensIn ?? '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Tokens Out">{data?.tokensOut ?? '—'}</InspectorFieldRow>
        </InspectorFieldGroup>
      </>
    );
    if (tab === 'prompt') return <InspectorJsonBlock value={data?.prompt?.messages ?? data?.prompt?.systemPrompt ?? '—'} />;
    if (tab === 'response') return <InspectorTextBlock text={data?.response?.content ?? data?.response?.rawResponse ?? '—'} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
