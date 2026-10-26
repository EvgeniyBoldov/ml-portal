import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceRoute } from '../../../traceProjection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const list = (items: string[]): string => items.length ? items.join('\n') : 'Нет';
const policyDispositionLabels: Record<string, string> = {
  accepted: 'Рекомендация принята',
  modified: 'Рекомендация уточнена',
  rejected: 'Рекомендация отклонена',
  not_applicable: 'Рекомендация не применялась',
};

/** Operator-facing view of the turn_preflight routing contract. */
export function RouteViewer({ route }: { route?: TraceRoute }) {
  if (!route) return <InspectorEmptyState message="Решение маршрутизации не записано в ответе preflight." />;
  return <InspectorFieldGroup>
    {route.proposed ? <InspectorFieldRow label="Предложенный маршрут"><InspectorScalar value={route.proposed} /></InspectorFieldRow> : null}
    {route.effective ? <InspectorFieldRow label="Эффективный маршрут"><InspectorScalar value={route.effective} /></InspectorFieldRow> : null}
    {route.policyDisposition ? <InspectorFieldRow label="Рекомендация политики"><InspectorScalar value={policyDispositionLabels[route.policyDisposition] ?? route.policyDisposition} /></InspectorFieldRow> : null}
    {route.policyRecommendationId ? <InspectorFieldRow label="ID рекомендации"><InspectorScalar value={route.policyRecommendationId} /></InspectorFieldRow> : null}
    {route.policyReasonCode ? <InspectorFieldRow label="Код решения"><InspectorScalar value={route.policyReasonCode} /></InspectorFieldRow> : null}
    {route.reason ? <InspectorFieldRow label="Основание"><InspectorScalar value={({ model_selected: 'Выбор модели', runtime_reroute: 'Перенаправлено runtime', policy_route: 'Маршрут по политике' } as Record<string, string>)[route.reason] ?? route.reason} /></InspectorFieldRow> : null}
    {route.detail ? <InspectorFieldRow label="Почему изменён"><InspectorTextBlock text={route.detail} /></InspectorFieldRow> : null}
    {route.goal ? <InspectorFieldRow label="Цель"><InspectorTextBlock text={route.goal} /></InspectorFieldRow> : null}
    {route.direction ? <InspectorFieldRow label="Направление"><InspectorTextBlock text={route.direction} /></InspectorFieldRow> : null}
    {route.expectedResult ? <InspectorFieldRow label="Ожидаемый результат"><InspectorTextBlock text={route.expectedResult} /></InspectorFieldRow> : null}
    <InspectorFieldRow label="Сущности"><InspectorTextBlock text={list(route.entityHints)} /></InspectorFieldRow>
    <InspectorFieldRow label="Проекты"><InspectorTextBlock text={list(route.projectHints)} /></InspectorFieldRow>
    <InspectorFieldRow label="Ограничения"><InspectorTextBlock text={list(route.constraints)} /></InspectorFieldRow>
    {route.input !== undefined ? <InspectorFieldRow label="Входные данные"><InspectorJsonBlock value={route.input} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>;
}
