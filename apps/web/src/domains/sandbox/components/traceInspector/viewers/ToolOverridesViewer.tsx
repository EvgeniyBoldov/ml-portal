import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar } from '@/shared/ui/Inspector';
import type { TraceToolOverrideSnapshot } from '../../../traceProjection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const operationLabel = (item: { toolId: string; operationSlug?: string; operationName?: string }): string => {
  if (item.operationName) return item.operationName;
  if (item.operationSlug) return item.operationSlug.split('.').join(' · ');
  return /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(item.toolId) ? 'Операция без названия' : item.toolId.split('.').join(' · ');
};

const publicationLabel = (configured?: boolean, effective?: boolean): string => {
  if (effective === true) return configured === false ? 'Доступна по умолчанию' : 'Доступна';
  if (effective === false) return 'Недоступна';
  return 'Статус не записан';
};

const reasonLabel = (reason?: string): string => reason === 'disabled_by_sandbox_override'
  ? 'Отключено настройкой песочницы' : reason || 'Причина не записана';

/** Shows configured overrides beside operations actually resolved for this run. */
export function ToolOverridesViewer({ snapshot }: { snapshot?: TraceToolOverrideSnapshot }) {
  if (!snapshot) return <InspectorEmptyState message="Снимок настроек операций для этого запуска не записан." />;
  return <InspectorFieldGroup>
    {Object.keys(snapshot.configuredPublication).length || Object.keys(snapshot.configuredSemantics).length ? <InspectorFieldRow label="Исходные настройки"><details><summary>Показать технические настройки</summary>
      {Object.keys(snapshot.configuredPublication).length ? <InspectorFieldRow label="Настройки публикации"><InspectorJsonBlock value={snapshot.configuredPublication} /></InspectorFieldRow> : null}
      {Object.keys(snapshot.configuredSemantics).length ? <InspectorFieldRow label="Настроенная семантика"><InspectorJsonBlock value={snapshot.configuredSemantics} /></InspectorFieldRow> : null}
    </details></InspectorFieldRow> : null}
    {snapshot.effectiveOperations.length ? <InspectorFieldRow label="Операции в этом запуске"><div>
      {snapshot.effectiveOperations.map((item, index) => <InspectorFieldGroup key={`${item.operationSlug ?? item.toolId}:${index}`}>
        <InspectorFieldRow label="Операция"><InspectorScalar value={operationLabel(item)} /></InspectorFieldRow>
        <InspectorFieldRow label="Доступность"><InspectorScalar value={publicationLabel(item.publicationConfigured, item.publishedEffective)} /></InspectorFieldRow>
        {item.effectiveSemantics !== undefined ? <InspectorFieldRow label="Эффективные настройки"><details><summary>Показать технические настройки</summary><InspectorJsonBlock value={item.effectiveSemantics} /></details></InspectorFieldRow> : null}
      </InspectorFieldGroup>)}
    </div></InspectorFieldRow> : null}
    {snapshot.suppressedPublication.length ? <InspectorFieldRow label="Не опубликованы">
      <div>{snapshot.suppressedPublication.map((item) => <InspectorFieldGroup key={item.toolId}>
        <InspectorFieldRow label="Операция"><InspectorScalar value={operationLabel(item)} /></InspectorFieldRow>
        <InspectorFieldRow label="Причина"><InspectorScalar value={reasonLabel(item.reason)} /></InspectorFieldRow>
      </InspectorFieldGroup>)}</div>
    </InspectorFieldRow> : null}
    {!Object.keys(snapshot.configuredPublication).length && !Object.keys(snapshot.configuredSemantics).length
      && !snapshot.effectiveOperations.length && !snapshot.suppressedPublication.length
      ? <InspectorFieldRow label="Операции"><InspectorScalar value="Нет данных" /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
