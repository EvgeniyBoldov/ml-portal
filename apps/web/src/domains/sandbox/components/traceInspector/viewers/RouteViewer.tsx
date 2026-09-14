import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceRoute } from '../../../traceProjection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const list = (items: string[]): string => items.length ? items.join('\n') : 'Нет';

/** Operator-facing view of the turn_preflight routing contract. */
export function RouteViewer({ route }: { route?: TraceRoute }) {
  if (!route) return <InspectorEmptyState message="Решение маршрутизации не записано в ответе preflight." />;
  return <InspectorFieldGroup>
    <InspectorFieldRow label="Куда"><InspectorScalar value={route.route} /></InspectorFieldRow>
    {route.goal ? <InspectorFieldRow label="Цель"><InspectorTextBlock text={route.goal} /></InspectorFieldRow> : null}
    {route.direction ? <InspectorFieldRow label="Направление"><InspectorTextBlock text={route.direction} /></InspectorFieldRow> : null}
    {route.expectedResult ? <InspectorFieldRow label="Ожидаемый результат"><InspectorTextBlock text={route.expectedResult} /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Сущности"><InspectorTextBlock text={list(route.entityHints)} /></InspectorFieldRow>
    <InspectorFieldRow label="Проекты"><InspectorTextBlock text={list(route.projectHints)} /></InspectorFieldRow>
    <InspectorFieldRow label="Ограничения"><InspectorTextBlock text={list(route.constraints)} /></InspectorFieldRow>
    {route.input !== undefined ? <InspectorFieldRow label="Входные данные"><InspectorJsonBlock value={route.input} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
