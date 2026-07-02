import { InspectorTabs } from '@/shared/ui/Inspector';
import { isRunData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, EntityErrorsTab, InfoTab, RawTab, SnapshotTextField, SnapshotValueField, getEntityContextSnapshot, getEntityErrors } from '../shared';
import { InspectorFieldGroup } from '@/shared/ui/Inspector';

export function RunInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isRunData(entity.data) ? entity.data : null;
  const snapshot = getEntityContextSnapshot(entity);
  const snapshotInputs = snapshot?.inputs;
  const snapshotMeta = snapshot?.meta;
  const hasErrors = getEntityErrors(entity).length > 0;
  const tabs = [
    { key: 'params', label: 'Параметры' },
    { key: 'response', label: 'Результат' },
    { key: 'budgets', label: 'Бюджет' },
    ...(hasErrors ? [{ key: 'errors', label: 'Ошибки' }] : []),
    { key: 'raw', label: 'RAW' },
  ];

  return (
    <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
      if (tab === 'params') {
        return (
          <InspectorFieldGroup>
            <InfoTab entity={entity} steps={steps} />
            <SnapshotTextField label="Запрос" text={String(snapshotInputs?.user_request ?? data?.userRequest ?? '—')} />
            <SnapshotValueField label="Агент" value={snapshotMeta?.agent_slug ?? snapshotMeta?.explicit_agent_slug ?? data?.agentSlug ?? '—'} />
            <SnapshotValueField label="Модель" value={snapshotMeta?.model ?? '—'} />
          </InspectorFieldGroup>
        );
      }
      if (tab === 'response') {
        return (
          <InspectorFieldGroup>
            {data?.finalContent ? <SnapshotTextField label="Ответ" text={data.finalContent} /> : null}
            {data?.finalError ? <SnapshotTextField label="Ошибка" text={data.finalError} /> : null}
            {!data?.finalContent && !data?.finalError ? <SnapshotTextField label="Результат" text="—" /> : null}
          </InspectorFieldGroup>
        );
      }
      if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
      if (tab === 'errors') return <EntityErrorsTab entity={entity} />;
      return <RawTab value={entity.data} entity={entity} steps={steps} />;
    }} />
  );
}
