import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorTabs } from '@/shared/ui/Inspector';
import {
  isAgentData,
  type PublishedCollectionSnapshot,
  type PublishedOperationSnapshot,
  type TraceEntity,
} from '@/domains/runtimeTrace/entityTypes';
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

function normalizeOperation(value: unknown): PublishedOperationSnapshot | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const rec = value as Record<string, unknown>;
  const slug = rec.operation_slug ?? rec.operation ?? rec.tool ?? rec.name;
  if (typeof slug !== 'string' || slug.trim().length === 0) return null;
  return {
    operation_slug: slug.trim(),
    canonical_name: typeof rec.canonical_name === 'string' ? rec.canonical_name : undefined,
    scope_kind: rec.scope_kind === 'system' || rec.scope_kind === 'collection' ? rec.scope_kind : undefined,
    domain: typeof rec.domain === 'string' ? rec.domain : undefined,
    title: typeof rec.title === 'string' ? rec.title : undefined,
    description: typeof rec.description === 'string' ? rec.description : undefined,
    result_kind: typeof rec.result_kind === 'string' ? rec.result_kind : undefined,
    collection_slug: typeof rec.collection_slug === 'string' ? rec.collection_slug : undefined,
    collection_type: typeof rec.collection_type === 'string' ? rec.collection_type : undefined,
    collection_purpose: typeof rec.collection_purpose === 'string' ? rec.collection_purpose : undefined,
    collection_readiness: typeof rec.collection_readiness === 'string' ? rec.collection_readiness : undefined,
    schema_freshness: typeof rec.schema_freshness === 'string' ? rec.schema_freshness : undefined,
    provider_kind: typeof rec.provider_kind === 'string' ? rec.provider_kind : undefined,
    input_schema_summary: Array.isArray(rec.input_schema_summary) ? rec.input_schema_summary.map(String) : undefined,
    side_effects: typeof rec.side_effects === 'boolean' ? rec.side_effects : undefined,
    risk_level: rec.risk_level === 'safe' || rec.risk_level === 'write' || rec.risk_level === 'destructive'
      ? rec.risk_level
      : undefined,
  };
}

function normalizeCollection(value: unknown): PublishedCollectionSnapshot | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const rec = value as Record<string, unknown>;
  if (typeof rec.collection_slug !== 'string' || rec.collection_slug.trim().length === 0) return null;
  return {
    collection_slug: rec.collection_slug.trim(),
    collection_type: typeof rec.collection_type === 'string' ? rec.collection_type : undefined,
    title: typeof rec.title === 'string' ? rec.title : undefined,
    purpose: typeof rec.purpose === 'string' ? rec.purpose : undefined,
    data_description: typeof rec.data_description === 'string' ? rec.data_description : undefined,
    readiness_status: typeof rec.readiness_status === 'string' ? rec.readiness_status : undefined,
    schema_freshness: typeof rec.schema_freshness === 'string' ? rec.schema_freshness : undefined,
    missing_requirements: Array.isArray(rec.missing_requirements) ? rec.missing_requirements.map(String) : undefined,
    available_operation_slugs: Array.isArray(rec.available_operation_slugs) ? rec.available_operation_slugs.map(String) : undefined,
  };
}

function normalizeUsedOperation(value: unknown): PublishedOperationSnapshot | null {
  const normalized = normalizeOperation(value);
  if (normalized) return normalized;
  if (typeof value === 'string' && value.trim().length > 0) {
    return { operation_slug: value.trim() };
  }
  return null;
}

function describeOperation(operation: PublishedOperationSnapshot): string {
  const title = operation.title?.trim() || operation.canonical_name?.trim() || operation.operation_slug;
  const parts = [];
  if (operation.description?.trim()) parts.push(operation.description.trim());
  if (operation.result_kind?.trim()) parts.push(`результат: ${operation.result_kind.trim()}`);
  if (operation.input_schema_summary && operation.input_schema_summary.length > 0) {
    parts.push(`аргументы: ${operation.input_schema_summary.join(', ')}`);
  }
  if (typeof operation.side_effects === 'boolean') {
    parts.push(operation.side_effects ? 'есть side effects' : 'без side effects');
  }
  if (operation.risk_level) parts.push(`риск: ${operation.risk_level}`);
  return parts.length > 0 ? `${title} — ${parts.join('; ')}` : title;
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

  const stepAvailableOperations = steps.flatMap((step) => {
    const stepData = (step.data ?? {}) as Record<string, unknown>;
    const direct = Array.isArray(stepData.available_operations) ? stepData.available_operations : [];
    const nestedSnapshot = stepData.context_snapshot as Record<string, unknown> | undefined;
    const fromSnapshot = (nestedSnapshot?.meta as Record<string, unknown> | undefined)?.available_operations;
    const nested = Array.isArray(fromSnapshot) ? fromSnapshot : [];
    return [...direct, ...nested]
      .map(normalizeOperation)
      .filter((item): item is PublishedOperationSnapshot => !!item);
  });

  const snapshotAvailableOperations = Array.isArray(snapshotMeta?.available_operations)
    ? snapshotMeta.available_operations.map(normalizeOperation).filter((item): item is PublishedOperationSnapshot => !!item)
    : [];
  const snapshotAvailableCollections = Array.isArray(snapshotMeta?.available_collections)
    ? snapshotMeta.available_collections.map(normalizeCollection).filter((item): item is PublishedCollectionSnapshot => !!item)
    : [];
  const availableOperationsMap = new Map<string, PublishedOperationSnapshot>();
  for (const operation of [...(data?.availableOperations ?? []), ...snapshotAvailableOperations, ...stepAvailableOperations]) {
    availableOperationsMap.set(operation.operation_slug, {
      ...availableOperationsMap.get(operation.operation_slug),
      ...operation,
    });
  }
  for (const slug of data?.toolsAvailable ?? []) {
    if (!availableOperationsMap.has(slug)) {
      availableOperationsMap.set(slug, { operation_slug: slug });
    }
  }
  const availableOperations = Array.from(availableOperationsMap.values()).sort((a, b) => a.operation_slug.localeCompare(b.operation_slug));
  const usedOperations = Array.from(new Map(
    steps
      .filter((step) => step.type === 'operation_call' || step.type === 'tool_call')
      .map((step) => {
        const stepData = (step.data ?? {}) as Record<string, unknown>;
        return normalizeUsedOperation(stepData.operation ?? stepData);
      })
      .filter((item): item is PublishedOperationSnapshot => !!item)
      .map((item) => [item.operation_slug, item] as const),
  ).values()).sort((a, b) => a.operation_slug.localeCompare(b.operation_slug));
  const collectionsMap = new Map<string, PublishedCollectionSnapshot>();
  for (const collection of [...(data?.availableCollections ?? []), ...snapshotAvailableCollections]) {
    collectionsMap.set(collection.collection_slug, collection);
  }
  for (const operation of availableOperations) {
    if (!operation.collection_slug || collectionsMap.has(operation.collection_slug)) continue;
    collectionsMap.set(operation.collection_slug, {
      collection_slug: operation.collection_slug,
      collection_type: operation.collection_type,
      purpose: operation.collection_purpose,
      readiness_status: operation.collection_readiness,
      schema_freshness: operation.schema_freshness,
    });
  }
  const availableCollections = Array.from(collectionsMap.values()).sort((a, b) => a.collection_slug.localeCompare(b.collection_slug));
  const operationsByCollection = new Map<string, PublishedOperationSnapshot[]>();
  const systemOperations: PublishedOperationSnapshot[] = [];
  for (const operation of availableOperations) {
    if (operation.scope_kind === 'system' || !operation.collection_slug) {
      systemOperations.push(operation);
      continue;
    }
    const current = operationsByCollection.get(operation.collection_slug) ?? [];
    current.push(operation);
    operationsByCollection.set(operation.collection_slug, current);
  }
  const usedOperationSlugs = new Set(usedOperations.map((item) => item.operation_slug));

  const rbac = (snapshotRbac ?? null) as Record<string, unknown> | null;
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
          <SnapshotValueField label="Доступно операций" value={String(availableOperations.length)} />
          <SnapshotValueField label="Использовано операций" value={String(usedOperations.length)} />
          <SnapshotValueField label="Коллекций" value={String(availableCollections.length)} />
          {availableCollections.map((collection) => {
            const collectionOps = (operationsByCollection.get(collection.collection_slug) ?? [])
              .sort((a, b) => a.operation_slug.localeCompare(b.operation_slug));
            return (
              <InspectorFieldGroup key={collection.collection_slug}>
                <InspectorFieldRow label={`Коллекция: ${collection.collection_slug}`}>
                  {[collection.collection_type, collection.readiness_status, collection.schema_freshness]
                    .filter(Boolean)
                    .join(' · ') || '—'}
                </InspectorFieldRow>
                <InspectorFieldRow label="Назначение">
                  {collection.purpose ?? collection.data_description ?? '—'}
                </InspectorFieldRow>
                <InspectorFieldRow label="Операции">
                  {collectionOps.length > 0
                    ? collectionOps.map((operation) => {
                      const prefix = usedOperationSlugs.has(operation.operation_slug) ? '[used] ' : '';
                      return `${prefix}${describeOperation(operation)}`;
                    }).join('\n')
                    : '—'}
                </InspectorFieldRow>
              </InspectorFieldGroup>
            );
          })}
          {availableCollections.length === 0 ? <InspectorFieldRow label="Коллекции">—</InspectorFieldRow> : null}
          <InspectorFieldRow label="Системные операции">
            {systemOperations.length > 0
              ? systemOperations
                .sort((a, b) => a.operation_slug.localeCompare(b.operation_slug))
                .map((operation) => {
                  const prefix = usedOperationSlugs.has(operation.operation_slug) ? '[used] ' : '';
                  return `${prefix}${describeOperation(operation)}`;
                }).join('\n')
              : '—'}
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
