import { InspectorFieldGroup, InspectorFieldRow, InspectorTabs } from '@/shared/ui/Inspector';
import { isDialogData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { BudgetsTab, InfoTab, RawTab, SnapshotTextField, SnapshotValueField } from '../shared';

export function DialogInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isDialogData(entity.data) ? entity.data : null;
  const items = data?.items?.length
    ? data.items
    : data?.question || data?.answer
      ? [{ question: data.question, answer: data.answer, resumeAction: undefined, sourceRunId: undefined }]
      : [];

  const tabs = [
    { key: 'info', label: 'Инфо' },
    { key: 'qa', label: 'Вопрос-ответ' },
    { key: 'budgets', label: 'Бюджет' },
    { key: 'raw', label: 'RAW' },
  ];

  return (
    <InspectorTabs
      entityId={entity.id}
      tabs={tabs}
      render={(tab) => {
        if (tab === 'info') {
          return (
            <>
              <InfoTab entity={entity} steps={steps} showTitle={false} />
              <InspectorFieldGroup>
                <SnapshotValueField label="Тип" value={data?.interactionKind === 'confirm' ? 'Подтверждение' : 'Уточнение'} />
                <SnapshotValueField label="Пар вопросов" value={items.length || '—'} />
                <SnapshotTextField label="Первый вопрос" text={items[0]?.question} />
                <SnapshotTextField label="Первый ответ" text={items[0]?.answer} />
              </InspectorFieldGroup>
            </>
          );
        }
        if (tab === 'qa') {
          return (
            <InspectorFieldGroup>
              {items.length > 0 ? items.map((item, index) => (
                <InspectorFieldGroup key={`${entity.id}-dialog-item-${index}`}>
                  <InspectorFieldRow label={`Пара ${index + 1}`}>
                    {item.resumeAction ? `resume=${item.resumeAction}` : '—'}
                  </InspectorFieldRow>
                  <SnapshotTextField label="Вопрос" text={item.question} />
                  <SnapshotTextField label="Ответ" text={item.answer} />
                  <InspectorFieldRow label="Источник">{item.sourceRunId ?? '—'}</InspectorFieldRow>
                </InspectorFieldGroup>
              )) : (
                <InspectorFieldRow label="Пары">—</InspectorFieldRow>
              )}
            </InspectorFieldGroup>
          );
        }
        if (tab === 'budgets') {
          return <BudgetsTab entity={entity} steps={steps} />;
        }
        return <RawTab value={entity.data} entity={entity} steps={steps} />;
      }}
    />
  );
}
