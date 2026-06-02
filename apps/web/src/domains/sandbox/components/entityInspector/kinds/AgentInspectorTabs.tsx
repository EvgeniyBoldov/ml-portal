import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorTabs } from '@/shared/ui/Inspector';
import { isAgentData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import {
  BudgetsTab,
  InfoTab,
  RawTab,
  SnapshotJsonField,
  SnapshotTextField,
  SnapshotValueField,
  getEntityInputsSnapshot,
  getEntityMetaSnapshot,
  getEntityRbacSnapshot,
  getPromptSnapshot,
} from '../shared';

function prettifySegment(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function splitOperationSlug(slug: string): { collection: string; label: string } {
  const cleaned = slug.trim();
  if (!cleaned) return { collection: 'Общее', label: 'unknown' };
  const parts = cleaned.split(/[./:]/).filter(Boolean);
  if (parts.length <= 1) {
    return { collection: 'Общее', label: prettifySegment(parts[0] ?? cleaned) };
  }
  const label = prettifySegment(parts.pop() ?? cleaned);
  const collection = prettifySegment(parts.join(' '));
  return { collection, label };
}

function groupOperationLabels(slugs: string[]): Array<{ collection: string; labels: string[] }> {
  const groups = new Map<string, Set<string>>();
  for (const slug of slugs) {
    const { collection, label } = splitOperationSlug(slug);
    const current = groups.get(collection) ?? new Set<string>();
    current.add(label);
    groups.set(collection, current);
  }
  return Array.from(groups.entries())
    .map(([collection, labels]) => ({
      collection,
      labels: Array.from(labels).sort((a, b) => a.localeCompare(b)),
    }))
    .sort((a, b) => a.collection.localeCompare(b.collection));
}

export function AgentInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isAgentData(entity.data) ? entity.data : null;
  const snapshotInputs = getEntityInputsSnapshot(entity);
  const snapshotMeta = getEntityMetaSnapshot(entity);
  const snapshotRbac = getEntityRbacSnapshot(entity);
  const slug = String(data?.slug ?? '').toLowerCase();
  const isFactsComponent = slug === 'facts' || slug === 'fact_extractor';
  const isSummaryComponent = slug === 'conversation' || slug === 'summary_compactor';
  const sourceIds = new Set(entity.sourceEventIds ?? []);
  const memoryResultStep = [...steps].reverse().find((s) => (
    (sourceIds.has(s.id) || String(s.data.parent_entity_id ?? '') === entity.id)
    && s.type === 'status'
    && String(s.data.stage ?? '') === 'memory_component_result'
  ));
  const factsResultStep = [...steps].reverse().find((s) => (
    String(s.data.parent_entity_id ?? '') === entity.id
    && s.type === 'status'
    && String(s.data.stage ?? '') === 'memory_facts_result'
  ));
  const summaryResultStep = [...steps].reverse().find((s) => (
    String(s.data.parent_entity_id ?? '') === entity.id
    && s.type === 'status'
    && String(s.data.stage ?? '') === 'memory_summary_result'
  ));
  const promptSnapshot = getPromptSnapshot(entity, steps) ?? '—';
  const extractedFacts = Array.isArray(factsResultStep?.data.facts)
    ? factsResultStep?.data.facts as Array<Record<string, unknown>>
    : [];
  const summaryPayload = (() => {
    const summary = summaryResultStep?.data.summary;
    if (!summary || typeof summary !== 'object') return null;
    const record = summary as Record<string, unknown>;
    return {
      goals: Array.isArray(record.goals) ? record.goals : [],
      done: Array.isArray(record.done) ? record.done : [],
      entities: (record.entities && typeof record.entities === 'object') ? record.entities : {},
      open_questions: Array.isArray(record.open_questions) ? record.open_questions : [],
      raw_tail: typeof record.raw_tail === 'string' ? record.raw_tail : '',
    };
  })();
  const tabs = isFactsComponent
    ? [{ key: 'info', label: 'Параметры' }, { key: 'facts', label: 'Факты' }, { key: 'prompt', label: 'Промпт' }, { key: 'budgets', label: 'Бюджет' }, { key: 'raw', label: 'RAW' }]
    : isSummaryComponent
      ? [{ key: 'info', label: 'Параметры' }, { key: 'result', label: 'Результат' }, { key: 'prompt', label: 'Промпт' }, { key: 'budgets', label: 'Бюджет' }, { key: 'raw', label: 'RAW' }]
      : [{ key: 'info', label: 'Параметры' }, { key: 'task', label: 'Задание' }, { key: 'prompt', label: 'Промпт' }, { key: 'tools', label: 'Инструменты' }, { key: 'rbac', label: 'RBAC' }, { key: 'budgets', label: 'Бюджет' }, { key: 'raw', label: 'RAW' }];

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
    const nestedSnapshot = stepData.context_snapshot as Record<string, unknown> | undefined;
    const fromSnapshot = (nestedSnapshot?.meta as Record<string, unknown> | undefined)?.available_operations;
    const nested = Array.isArray(fromSnapshot) ? fromSnapshot : [];
    return [...direct, ...nested]
      .map(extractOperationSlug)
      .filter((item): item is string => !!item);
  });

  const snapshotAvailableOperations = Array.isArray(snapshotMeta?.available_operations)
    ? snapshotMeta.available_operations.map(String)
    : [];
  const availableOperations = Array.from(new Set([...(data?.toolsAvailable ?? []), ...snapshotAvailableOperations, ...stepAvailableOperations])).sort((a, b) => a.localeCompare(b));
  const usedOperations = Array.from(new Set(
    steps
      .filter((step) => step.type === 'operation_call' || step.type === 'tool_call')
      .map((step) => {
        const stepData = (step.data ?? {}) as Record<string, unknown>;
        return extractOperationSlug(stepData.operation_slug ?? stepData.operation ?? stepData.tool);
      })
      .filter((item): item is string => !!item),
  )).sort((a, b) => a.localeCompare(b));
  const availableOperationGroups = groupOperationLabels(availableOperations);
  const usedOperationGroups = groupOperationLabels(usedOperations);

  const rbacSnapshot = [...steps]
    .reverse()
    .find((s) => (
      s.type === 'status'
      && String(s.data.stage ?? '') === 'agent_rbac_snapshot'
      && String((s.data.agent_slug ?? '')).trim() === String(data?.slug ?? '').trim()
    ));
  const rbac = (snapshotRbac ?? rbacSnapshot?.data.rbac ?? null) as Record<string, unknown> | null;
  const taskInput = snapshotInputs?.agent_input;
  const taskText = typeof taskInput === 'string'
    ? taskInput
    : taskInput && typeof taskInput === 'object'
      ? JSON.stringify(taskInput, null, 2)
      : '—';

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') {
      return (
        <InspectorFieldGroup>
          <InfoTab entity={entity} steps={steps} showTitle={false} />
          <SnapshotValueField label="Роль" value={snapshotMeta?.role ?? data?.slug ?? '—'} />
          <SnapshotValueField label="Модель" value={snapshotMeta?.model ?? '—'} />
          {!isFactsComponent && !isSummaryComponent ? (
            <>
              <SnapshotValueField label="Slug" value={data?.slug ?? snapshotMeta?.agent_slug ?? '—'} />
              <SnapshotValueField label="Версия" value={data?.versionLabel ?? snapshotMeta?.version_label ?? '—'} />
            </>
          ) : null}
        </InspectorFieldGroup>
      );
    }
    if (tab === 'facts' && isFactsComponent) {
      return (
        <InspectorFieldGroup>
          {!factsResultStep ? 'Нет структурированного результата' : null}
          <SnapshotJsonField label="Факты" value={extractedFacts.length > 0 ? extractedFacts : []} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'result' && isSummaryComponent) {
      return (
        <InspectorFieldGroup>
          {!summaryResultStep ? <InspectorFieldRow label="Результат">Нет структурированного результата</InspectorFieldRow> : null}
          <SnapshotTextField label="Промпт" text={promptSnapshot} />
          <SnapshotValueField label="Целей" value={summaryPayload?.goals?.length ?? 0} />
          <SnapshotValueField label="Сделано" value={summaryPayload?.done?.length ?? 0} />
          <SnapshotValueField label="Открытых вопросов" value={summaryPayload?.open_questions?.length ?? 0} />
          <InspectorFieldRow label="Цели">{summaryPayload?.goals.length ? summaryPayload.goals.join(', ') : '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Сделано">{summaryPayload?.done.length ? summaryPayload.done.join(', ') : '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Сущности">{Object.keys(summaryPayload?.entities ?? {}).length ? Object.keys(summaryPayload?.entities ?? {}).join(', ') : '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Открытые вопросы">{summaryPayload?.open_questions.length ? summaryPayload.open_questions.join(', ') : '—'}</InspectorFieldRow>
        </InspectorFieldGroup>
      );
    }
    if (tab === 'task' && !isFactsComponent && !isSummaryComponent) {
      return (
        <InspectorFieldGroup>
          <SnapshotTextField label="Задание" text={taskText} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'prompt') {
      return (
        <InspectorFieldGroup>
          <SnapshotTextField label="Промпт" text={promptSnapshot} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'tools') {
      return (
        <InspectorFieldGroup>
          <SnapshotValueField label="Доступно всего" value={String(availableOperations.length)} />
          <SnapshotValueField label="Использовано всего" value={String(usedOperations.length)} />
          {availableOperationGroups.map((group) => (
            <InspectorFieldRow key={`available-${group.collection}`} label={`Доступно: ${group.collection}`}>
              {group.labels.join(', ')}
            </InspectorFieldRow>
          ))}
          {availableOperationGroups.length === 0 ? <InspectorFieldRow label="Доступно">—</InspectorFieldRow> : null}
          {usedOperationGroups.map((group) => (
            <InspectorFieldRow key={`used-${group.collection}`} label={`Использовано: ${group.collection}`}>
              {group.labels.join(', ')}
            </InspectorFieldRow>
          ))}
          {usedOperationGroups.length === 0 ? <InspectorFieldRow label="Использовано">—</InspectorFieldRow> : null}
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
      const deniedLegacy = Array.isArray(rbac.denied) ? rbac.denied.map(String) : [];
      const denied = Array.from(new Set([...deniedByRbac, ...deniedByCapability]));
      return (
        <InspectorFieldGroup>
          <SnapshotValueField label="Доступно" value={String(allowed.length)} />
          <SnapshotValueField label="Отклонено" value={String(denied.length || deniedLegacy.length)} />
          <InspectorFieldRow label="Разрешено">{allowed.length ? allowed.join(', ') : '—'}</InspectorFieldRow>
          <InspectorFieldRow label="Отклонено">{(denied.length ? denied : deniedLegacy).length ? (denied.length ? denied : deniedLegacy).join(', ') : '—'}</InspectorFieldRow>
        </InspectorFieldGroup>
      );
    }
    const rawValue = memoryResultStep ? { ...entity.data, memory_component_result: memoryResultStep.data } : entity.data;
    return <RawTab value={rawValue} entity={entity} steps={steps} />;
  }} />;
}
