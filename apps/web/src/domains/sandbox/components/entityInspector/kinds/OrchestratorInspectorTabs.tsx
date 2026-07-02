import { InspectorTabs, InspectorFieldGroup } from '@/shared/ui/Inspector';
import { isOrchestratorData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, EntityErrorsTab, InfoTab, RawTab, SnapshotTextField, SnapshotValueField, SpendTab, getEntityContextSnapshot, getEntityErrors, getPromptSnapshot } from '../shared';

export function OrchestratorInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isOrchestratorData(entity.data) ? entity.data : null;
  const snapshot = getEntityContextSnapshot(entity);
  const snapshotInputs = snapshot?.inputs;
  const snapshotMeta = snapshot?.meta;
  const snapshotRbac = snapshot?.rbac;
  const isPhase = entity.kind === 'phase' && entity.data.kind === 'phase';
  const promptSnapshot = getPromptSnapshot(entity, steps) ?? '—';
  const hasErrors = getEntityErrors(entity).length > 0;
  const tabs = isPhase
    ? [
      { key: 'info', label: 'Инфо' },
      { key: 'spend', label: 'Расход' },
      ...(hasErrors ? [{ key: 'errors', label: 'Ошибки' }] : []),
      { key: 'raw', label: 'RAW' },
    ]
    : [
      { key: 'info', label: 'Параметры' },
      { key: 'prompt', label: 'Промпт' },
      ...(snapshotRbac ? [{ key: 'rbac', label: 'RBAC' }] : []),
      { key: 'budgets', label: 'Бюджет' },
      ...(hasErrors ? [{ key: 'errors', label: 'Ошибки' }] : []),
      { key: 'raw', label: 'RAW' },
    ];

  return (
    <InspectorTabs
      entityId={entity.id}
      tabs={tabs}
      render={(tab) => {
        if (tab === 'info') {
          if (isPhase) return <InfoTab entity={entity} steps={steps} showTitle={false} />;
          return (
            <InspectorFieldGroup>
              <InfoTab entity={entity} steps={steps} showTitle={false} />
              <SnapshotValueField label="Роль" value={snapshotMeta?.role ?? data?.role ?? '—'} />
              <SnapshotValueField label="Модель" value={snapshotMeta?.model ?? '—'} />
              <SnapshotTextField label="Цель" text={String(snapshotInputs?.goal ?? '—')} />
              <SnapshotTextField label="Подсказка планера" text={String(snapshotInputs?.planner_hint ?? '—')} />
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
        if (tab === 'spend') return <SpendTab entity={entity} />;
        if (tab === 'errors') return <EntityErrorsTab entity={entity} />;
        if (tab === 'rbac') {
          return (
            <InspectorFieldGroup>
              <SnapshotValueField label="Кандидаты" value={snapshotRbac?.candidates?.length ?? '—'} />
              <SnapshotValueField label="Разрешено" value={snapshotRbac?.allowed?.length ?? '—'} />
              <SnapshotValueField label="Отклонено" value={(snapshotRbac?.denied?.length ?? snapshotRbac?.denied_by_rbac?.length ?? 0) || '—'} />
              <SnapshotTextField label="Доступные" text={snapshotRbac?.allowed?.length ? snapshotRbac.allowed.join(', ') : '—'} />
              <SnapshotTextField label="Недоступные" text={(snapshotRbac?.denied?.length ? snapshotRbac.denied.join(', ') : snapshotRbac?.denied_by_rbac?.join(', ')) || '—'} />
            </InspectorFieldGroup>
          );
        }
        if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
        return <RawTab value={entity.data} entity={entity} steps={steps} />;
      }}
    />
  );
}
