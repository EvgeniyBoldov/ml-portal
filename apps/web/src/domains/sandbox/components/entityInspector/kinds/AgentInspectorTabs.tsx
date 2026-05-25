import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorTabs, InspectorTextBlock } from '@/shared/ui/Inspector';
import { isAgentData, isLLMData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function AgentInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isAgentData(entity.data) ? entity.data : null;
  const llmChild = entity.children?.find((c) => c.kind === 'llm');
  const llmData = llmChild && isLLMData(llmChild.data) ? llmChild.data : null;
  const tabs = [{ key: 'info', label: 'Info' }, { key: 'prompt', label: 'Prompt' }, { key: 'response', label: 'Response' }, { key: 'tools', label: 'Tools' }, { key: 'budgets', label: 'Budgets' }, { key: 'rbac', label: 'RBAC' }, { key: 'raw', label: 'Raw' }];

  const extractOperationSlug = (value: unknown): string | null => {
    if (typeof value === 'string' && value.trim().length > 0) return value.trim();
    if (!value || typeof value !== 'object') return null;
    const rec = value as Record<string, unknown>;
    const slug = rec.operation_slug ?? rec.operation ?? rec.tool ?? rec.name;
    return typeof slug === 'string' && slug.trim().length > 0 ? slug.trim() : null;
  };

  const stepAvailableOperations = steps.flatMap((step) => {
    const stepData = (step.data ?? {}) as Record<string, unknown>;
    const direct = Array.isArray(stepData.available_operations) ? stepData.available_operations : [];
    const fromSnapshot = ((stepData.context_snapshot as Record<string, unknown> | undefined)?.available_operations);
    const nested = Array.isArray(fromSnapshot) ? fromSnapshot : [];
    return [...direct, ...nested]
      .map(extractOperationSlug)
      .filter((item): item is string => !!item);
  });

  const availableOperations = Array.from(new Set([...(data?.toolsAvailable ?? []), ...stepAvailableOperations])).sort((a, b) => a.localeCompare(b));
  const usedOperations = Array.from(new Set(
    steps
      .filter((step) => step.type === 'operation_call' || step.type === 'tool_call')
      .map((step) => {
        const stepData = (step.data ?? {}) as Record<string, unknown>;
        return extractOperationSlug(stepData.operation_slug ?? stepData.operation ?? stepData.tool);
      })
      .filter((item): item is string => !!item),
  )).sort((a, b) => a.localeCompare(b));

  const rbacSnapshot = [...steps]
    .reverse()
    .find((s) => (
      s.type === 'status'
      && String(s.data.stage ?? '') === 'agent_rbac_snapshot'
      && String((s.data.agent_slug ?? '')).trim() === String(data?.slug ?? '').trim()
    ));
  const rbac = (rbacSnapshot?.data.rbac ?? null) as Record<string, unknown> | null;

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return <InfoTab entity={entity} steps={steps} />;
    if (tab === 'prompt') {
      if (llmData?.prompt?.isBriefMode) {
        return <InspectorNotice tone="info" title="Brief Logging" message="Messages не сохранены" />;
      }
      return <InspectorJsonBlock value={llmData?.prompt?.messages ?? llmData?.prompt?.systemPrompt ?? data?.prompt?.systemPrompt ?? '—'} />;
    }
    if (tab === 'response') return <InspectorTextBlock text={llmData?.response?.content ?? llmData?.response?.rawResponse ?? '—'} />;
    if (tab === 'tools') {
      return (
        <InspectorFieldGroup>
          <InspectorFieldRow label="Available">
            {availableOperations.length > 0 ? availableOperations.join('\n') : '—'}
          </InspectorFieldRow>
          <InspectorFieldRow label="Used">
            {usedOperations.length > 0 ? usedOperations.join('\n') : '—'}
          </InspectorFieldRow>
        </InspectorFieldGroup>
      );
    }
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    if (tab === 'rbac') {
      if (!rbac) {
        return <InspectorNotice tone="neutral" title="RBAC Snapshot" message="Снимок RBAC для агента не найден" />;
      }
      const allowed = Array.isArray(rbac.allowed) ? rbac.allowed.map(String) : [];
      const deniedByRbac = Array.isArray(rbac.denied_by_rbac) ? rbac.denied_by_rbac.map(String) : [];
      const deniedByCapability = Array.isArray(rbac.denied_by_capability) ? rbac.denied_by_capability.map(String) : [];
      const bound = Array.isArray(rbac.capability_bound_collections) ? rbac.capability_bound_collections.map(String) : [];
      return (
        <InspectorFieldGroup>
          <InspectorFieldRow label="Slug">{data?.slug ?? '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Version">{data?.versionLabel ?? data?.versionId ?? '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Capability Bind">{bound.length ? bound.join(', ') : 'all'}</InspectorFieldRow>
          <InspectorFieldRow label="Allowed">{allowed.length ? allowed.join(', ') : '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Denied RBAC">{deniedByRbac.length ? deniedByRbac.join(', ') : '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Denied Capability">{deniedByCapability.length ? deniedByCapability.join(', ') : '—'}</InspectorFieldRow>
        </InspectorFieldGroup>
      );
    }
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
