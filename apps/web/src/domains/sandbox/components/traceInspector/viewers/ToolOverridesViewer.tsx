import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar } from '@/shared/ui/Inspector';
import type { TraceToolOverrideSnapshot } from '../../../traceProjection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const reasonLabel = (reason?: string): string => reason === 'disabled_by_sandbox_override'
  ? 'Отключено настройкой песочницы' : reason || 'Причина не записана';

/** Shows configured overrides beside operations actually resolved for this run. */
export function ToolOverridesViewer({ snapshot }: { snapshot?: TraceToolOverrideSnapshot }) {
  if (!snapshot) return <InspectorEmptyState message="Снимок настроек операций для этого запуска не записан." />;
  return <InspectorFieldGroup>
    {Object.keys(snapshot.configuredPublication).length ? <InspectorFieldRow label="Настройки публикации"><InspectorJsonBlock value={snapshot.configuredPublication} /></InspectorFieldRow> : null}
    {Object.keys(snapshot.configuredSemantics).length ? <InspectorFieldRow label="Настроенная семантика"><InspectorJsonBlock value={snapshot.configuredSemantics} /></InspectorFieldRow> : null}
    {snapshot.effectiveOperations.length ? <InspectorFieldRow label="Фактически доступные операции"><InspectorJsonBlock value={snapshot.effectiveOperations.map((item) => ({
      operation: item.toolId,
      publicationConfigured: item.publicationConfigured,
      publishedEffective: item.publishedEffective,
      configuredSemantics: item.configuredSemantics,
      effectiveSemantics: item.effectiveSemantics,
    }))} /></InspectorFieldRow> : null}
    {snapshot.suppressedPublication.length ? <InspectorFieldRow label="Не опубликованы">
      <InspectorJsonBlock value={snapshot.suppressedPublication.map((item) => ({ operation: item.toolId, reason: reasonLabel(item.reason) }))} />
    </InspectorFieldRow> : null}
    {!Object.keys(snapshot.configuredPublication).length && !Object.keys(snapshot.configuredSemantics).length
      && !snapshot.effectiveOperations.length && !snapshot.suppressedPublication.length
      ? <InspectorFieldRow label="Операции"><InspectorScalar value="Нет данных" /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
