import { InspectorFieldGroup, InspectorTabs } from '@/shared/ui/Inspector';
import { isLLMData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab, SnapshotJsonField, SnapshotValueField } from '../shared';

export function LlmInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isLLMData(entity.data) ? entity.data : null;
  const sourceSteps = steps.filter((s) => (
    entity.sourceEventIds.includes(s.id)
    || String((s.data as Record<string, unknown>)?.parent_entity_id ?? '') === entity.id
    || String((s.data as Record<string, unknown>)?.entity_id ?? '') === entity.id
  ));
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
  ];
  const responseKeys = [
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
  ];

  const requestPayload = pick(requestPayloadRaw, requestKeys);
  const responsePayload = pick(responsePayloadRaw, responseKeys);
  const tabs = [
    { key: 'info', label: 'Инфо' },
    { key: 'request', label: 'Реквест' },
    { key: 'response', label: 'Респонс' },
    { key: 'budgets', label: 'Бюджет' },
    { key: 'raw', label: 'RAW' },
  ];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return (
      <>
        <InfoTab entity={entity} steps={steps} />
        <InspectorFieldGroup>
          <SnapshotValueField label="Назначение" value={data?.purpose ?? '—'} />
          <SnapshotValueField label="Модель" value={data?.params?.model ?? '—'} />
          <SnapshotValueField label="Токены in" value={data?.tokensIn ?? '—'} />
          <SnapshotValueField label="Токены out" value={data?.tokensOut ?? '—'} />
          <SnapshotValueField label="Токены" value={data?.tokensTotal ?? '—'} />
          <SnapshotValueField
            label="Длительность"
            value={typeof responsePayloadRaw?.duration_ms === 'number'
              ? `${(responsePayloadRaw.duration_ms / 1000).toFixed(1).replace('.', ',')} s`
              : '—'}
          />
        </InspectorFieldGroup>
      </>
    );
    if (tab === 'request') {
      return (
        <InspectorFieldGroup>
          <SnapshotJsonField label="Реквест" value={requestPayload ?? data?.prompt?.messages ?? data?.prompt?.systemPrompt ?? '—'} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'response') {
      return (
        <InspectorFieldGroup>
          <SnapshotJsonField label="Респонс" value={responsePayload ?? data?.response?.content ?? data?.response?.rawResponse ?? '—'} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
