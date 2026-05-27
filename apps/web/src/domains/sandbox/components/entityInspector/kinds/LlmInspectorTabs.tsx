import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorTabs } from '@/shared/ui/Inspector';
import { isLLMData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function LlmInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isLLMData(entity.data) ? entity.data : null;
  const sourceSteps = steps.filter((s) => entity.sourceEventIds.includes(s.id));
  const requestStep = sourceSteps.find((s) => s.type === 'llm_turn' || s.type === 'llm_request' || s.type === 'llm_call');
  const responseStep = [...sourceSteps].reverse().find((s) => s.type === 'llm_turn' || s.type === 'llm_response' || s.type === 'llm_call');
  const requestPayloadRaw = (requestStep?.data ?? null) as Record<string, unknown> | null;
  const responsePayloadRaw = (responseStep?.data ?? null) as Record<string, unknown> | null;

  const pick = (input: Record<string, unknown> | null, keys: string[]): Record<string, unknown> | null => {
    if (!input) return null;
    const out: Record<string, unknown> = {};
    for (const key of keys) {
      if (Object.prototype.hasOwnProperty.call(input, key)) out[key] = input[key];
    }
    return Object.keys(out).length ? out : null;
  };

  const requestKeys = [
    'llm_call_id',
    'model',
    'purpose',
    'messages',
    'messages_sent',
    'system_prompt',
    'compiled_prompt',
    'prompt',
    'max_tokens',
    'temperature',
    'stop',
    'stop_sequences',
    'native_tool_calling',
    'step',
    'agent_slug',
    'agent_run_id',
    'parent_entity_type',
    'parent_entity_id',
    'actor_type',
    'actor_entity_id',
    'planner_iteration_id',
    'planner_run_id',
  ];
  const responseKeys = [
    'llm_call_id',
    'content',
    'response',
    'text',
    'parsed_response',
    'response_length',
    'tokens_in',
    'tokens_out',
    'tokens_total',
    'duration_ms',
    'finish_reason',
    'error',
    'error_code',
    'step',
    'agent_slug',
    'agent_run_id',
    'parent_entity_type',
    'parent_entity_id',
    'actor_type',
    'actor_entity_id',
    'planner_iteration_id',
    'planner_run_id',
  ];

  const requestPayload = pick(requestPayloadRaw, requestKeys);
  const responsePayload = pick(responsePayloadRaw, responseKeys);
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'request', label: 'Request' }, { key: 'response', label: 'Response' }, { key: 'budgets', label: 'Budgets' }, { key: 'raw', label: 'Raw' }];

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
    if (tab === 'request') return <InspectorJsonBlock value={requestPayload ?? data?.prompt?.messages ?? data?.prompt?.systemPrompt ?? '—'} />;
    if (tab === 'response') return <InspectorJsonBlock value={responsePayload ?? data?.response?.content ?? data?.response?.rawResponse ?? '—'} />;
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
