import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorTabs } from '@/shared/ui/Inspector';
import { isAgentData, isLLMData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab } from '../shared';

export function AgentInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isAgentData(entity.data) ? entity.data : null;
  const slug = String(data?.slug ?? '').toLowerCase();
  const isFactsComponent = slug === 'facts' || slug === 'fact_extractor';
  const isSummaryComponent = slug === 'conversation' || slug === 'summary_compactor';
  const sourceIds = new Set(entity.sourceEventIds ?? []);
  const memoryResultStep = [...steps].reverse().find((s) => (
    (sourceIds.has(s.id) || String(s.data.parent_entity_id ?? '') === entity.id)
    && s.type === 'status'
    && String(s.data.stage ?? '') === 'memory_component_result'
  ));
  const llmChildren = (entity.children ?? []).filter((c) => c.kind === 'llm' && isLLMData(c.data));
  const llmWithPrompt = llmChildren.find((c) => {
    if (!isLLMData(c.data)) return false;
    const llm = c.data;
    return !!(llm.prompt?.messages?.length || llm.prompt?.systemPrompt);
  });
  const llmPromptData = llmWithPrompt && isLLMData(llmWithPrompt.data) ? llmWithPrompt.data : null;
  const llmResultData = llmWithPrompt && isLLMData(llmWithPrompt.data) ? llmWithPrompt.data : null;
  const parsed = (() => {
    const raw = llmResultData?.response?.rawResponse ?? llmResultData?.response?.content;
    if (typeof raw !== 'string') return null;
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null;
    }
  })();
  const extractedFacts = Array.isArray(parsed?.facts)
    ? parsed?.facts as Array<Record<string, unknown>>
    : [];
  const summaryPayload = (() => {
    if (!parsed) return null;
    const summary = (parsed.summary && typeof parsed.summary === 'object') ? parsed.summary as Record<string, unknown> : parsed;
    return {
      goals: Array.isArray(summary.goals) ? summary.goals : [],
      done: Array.isArray(summary.done) ? summary.done : [],
      entities: (summary.entities && typeof summary.entities === 'object') ? summary.entities : {},
      open_questions: Array.isArray(summary.open_questions) ? summary.open_questions : [],
      raw_tail: typeof summary.raw_tail === 'string' ? summary.raw_tail : '',
    };
  })();
  const tabs = isFactsComponent
    ? [{ key: 'info', label: 'Инфо' }, { key: 'facts', label: 'Факты' }, { key: 'prompt', label: 'Промт' }, { key: 'budgets', label: 'Бюджет' }, { key: 'raw', label: 'RAW' }]
    : isSummaryComponent
      ? [{ key: 'info', label: 'Инфо' }, { key: 'result', label: 'Результат' }, { key: 'prompt', label: 'Промт' }, { key: 'budgets', label: 'Бюджет' }, { key: 'raw', label: 'RAW' }]
      : [{ key: 'info', label: 'Инфо' }, { key: 'prompt', label: 'Промт' }, { key: 'tools', label: 'Tools' }, { key: 'budgets', label: 'Бюджет' }, { key: 'rbac', label: 'RBAC' }, { key: 'raw', label: 'RAW' }];

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
    if (tab === 'facts' && isFactsComponent) {
      return (
        <InspectorFieldGroup>
          <InspectorJsonBlock value={extractedFacts.length > 0 ? extractedFacts : []} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'result' && isSummaryComponent) {
      return (
        <InspectorFieldGroup>
          <InspectorFieldRow label="Goals">
            <InspectorJsonBlock value={summaryPayload?.goals ?? []} />
          </InspectorFieldRow>
          <InspectorFieldRow label="Done">
            <InspectorJsonBlock value={summaryPayload?.done ?? []} />
          </InspectorFieldRow>
          <InspectorFieldRow label="Entities">
            <InspectorJsonBlock value={summaryPayload?.entities ?? {}} />
          </InspectorFieldRow>
          <InspectorFieldRow label="Open Questions">
            <InspectorJsonBlock value={summaryPayload?.open_questions ?? []} />
          </InspectorFieldRow>
        </InspectorFieldGroup>
      );
    }
    if (tab === 'prompt') {
      if (llmPromptData?.prompt?.isBriefMode) {
        return <InspectorNotice tone="info" title="Brief Logging" message="Messages не сохранены" />;
      }
      const promptMessages: Array<Record<string, unknown>> = llmPromptData?.prompt?.messages ?? [];
      const systemPromptFromMessages = promptMessages.find((msg: Record<string, unknown>) => String(msg.role ?? '') === 'system');
      const promptSnapshot = llmPromptData?.prompt?.systemPrompt
        ?? (typeof systemPromptFromMessages?.content === 'string' ? systemPromptFromMessages.content : undefined)
        ?? data?.prompt?.systemPrompt
        ?? '—';
      return (
        <InspectorFieldGroup>
          <InspectorJsonBlock value={promptSnapshot} />
        </InspectorFieldGroup>
      );
    }
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
    return <RawTab value={{ ...entity.data, memory_component_result: memoryResultStep?.data ?? null }} entity={entity} steps={steps} />;
  }} />;
}
