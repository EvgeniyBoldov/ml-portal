import { InspectorTabs } from '@/shared/ui/Inspector';
import { isToolData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab, SnapshotCodeField, SnapshotJsonField, SnapshotValueField } from '../shared';
import { InspectorFieldGroup } from '@/shared/ui/Inspector';

export function ToolInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isToolData(entity.data) ? entity.data : null;
  const outputValue = data?.result?.success
    ? (data?.result?.data ?? { success: true })
    : {
        success: false,
        error: data?.result?.error ?? 'Operation failed',
        errorCode: data?.result?.errorCode,
        retryable: data?.result?.retryable,
      };
  const hasErrors = !!(data?.result?.error || data?.result?.errorCode || (data?.retries && data.retries.length > 0));
  const tabs = [
    { key: 'info', label: 'Инфо' },
    { key: 'input', label: 'Реквест' },
    { key: 'output', label: 'Респонс' },
    { key: 'budgets', label: 'Бюджет' },
    ...(hasErrors ? [{ key: 'errors', label: 'Ошибки' }] : []),
    { key: 'raw', label: 'RAW' },
  ];

  return <InspectorTabs entityId={entity.id} tabs={tabs} render={(tab) => {
    if (tab === 'info') return (
      <>
        <InfoTab entity={entity} steps={steps} />
        <InspectorFieldGroup>
          <SnapshotCodeField label="Тул" value={data?.toolSlug ?? '—'} />
          <SnapshotCodeField label="Агент" value={data?.calledByAgentSlug ?? '—'} />
          <SnapshotValueField label="Статус" value={data?.result?.success ? 'Успешно' : 'Ошибка'} />
        </InspectorFieldGroup>
      </>
    );
    if (tab === 'input') {
      return (
        <InspectorFieldGroup>
          <SnapshotJsonField label="Реквест" value={data?.arguments ?? '—'} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'output') {
      return (
        <InspectorFieldGroup>
          <SnapshotJsonField label="Респонс" value={outputValue} />
        </InspectorFieldGroup>
      );
    }
    if (tab === 'budgets') return <BudgetsTab entity={entity} steps={steps} />;
    if (tab === 'errors') {
      return (
        <InspectorFieldGroup>
          <SnapshotJsonField
            label="Ошибки"
            value={{ error: data?.result?.error ?? null, errorCode: data?.result?.errorCode ?? null, retryable: data?.result?.retryable ?? null, retries: data?.retries ?? [] }}
          />
        </InspectorFieldGroup>
      );
    }
    return <RawTab value={entity.data} entity={entity} steps={steps} />;
  }} />;
}
