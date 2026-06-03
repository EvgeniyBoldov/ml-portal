import { InspectorFieldGroup, InspectorTabs } from '@/shared/ui/Inspector';
import { isInteractionData, type TraceEntity } from '@/domains/runtimeTrace/entityTypes';
import type { RunStep } from '../../../hooks/useSandboxRun';
import { InfoTab, SnapshotJsonField, SnapshotTextField, SnapshotValueField } from '../shared';

export function InteractionInspectorTabs({ entity, steps }: { entity: TraceEntity; steps: RunStep[] }) {
  const data = isInteractionData(entity.data) ? entity.data : null;
  const tabs = [
    { key: 'qa', label: 'Вопрос-ответ' },
    { key: 'raw', label: 'RAW' },
  ];

  return (
    <InspectorTabs
      entityId={entity.id}
      tabs={tabs}
      render={(tab) => {
        if (tab === 'qa') {
          return (
            <InspectorFieldGroup>
              <InfoTab entity={entity} steps={steps} showTitle={false} />
              <SnapshotValueField
                label="Тип"
                value={data?.interactionKind === 'confirm' ? 'Подтверждение' : 'Уточнение'}
              />
              <SnapshotTextField label="Вопрос" text={data?.question} />
              <SnapshotTextField label="Ответ пользователя" text={data?.answer} />
            </InspectorFieldGroup>
          );
        }
        if (tab === 'raw') {
          return (
            <InspectorFieldGroup>
              <SnapshotJsonField label="RAW" value={data ?? entity.data} />
            </InspectorFieldGroup>
          );
        }
        return null;
      }}
    />
  );
}
