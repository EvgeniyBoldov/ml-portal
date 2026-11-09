import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TracePreflight, TraceRoute } from '../../../traceProjection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const list = (items: string[]): string => items.length ? items.join('\n') : 'Нет';
const policyDispositionLabels: Record<string, string> = {
  accepted: 'Рекомендация принята',
  modified: 'Рекомендация уточнена',
  rejected: 'Рекомендация отклонена',
  not_applicable: 'Рекомендация не применялась',
};

/** Operator-facing view of the turn_preflight routing contract. */
const preflightStatus = (status: string): { label: string; tone: 'success' | 'warn' | 'danger' | 'neutral' } => {
  const value = status.toLowerCase();
  if (['completed', 'ready', 'succeeded', 'success'].includes(value)) return { label: 'Проверка завершена', tone: 'success' };
  if (['failed', 'error', 'blocked'].includes(value)) return { label: 'Проверка не пройдена', tone: 'danger' };
  if (['running', 'pending'].includes(value)) return { label: 'Проверка выполняется', tone: 'warn' };
  return { label: 'Состояние проверки неизвестно', tone: 'neutral' };
};

export function RouteViewer({ route, readiness }: { route?: TraceRoute; readiness?: TracePreflight }) {
  if (!route && !readiness) return <InspectorEmptyState message="Решение маршрутизации не записано в ответе preflight." />;
  const status = readiness ? preflightStatus(readiness.status) : undefined;
  const missing = readiness?.missing;
  return <InspectorFieldGroup>
    {status ? <InspectorFieldRow label="Готовность"><InspectorStatus label={status.label} tone={status.tone} /></InspectorFieldRow> : null}
    {readiness?.mode ? <InspectorFieldRow label="Режим проверки"><InspectorScalar value={readiness.mode} /></InspectorFieldRow> : null}
    {readiness?.operationsCount !== undefined ? <InspectorFieldRow label="Доступные операции"><InspectorScalar value={readiness.operationsCount} /></InspectorFieldRow> : null}
    {readiness?.dataInstancesCount !== undefined ? <InspectorFieldRow label="Подключённые источники данных"><InspectorScalar value={readiness.dataInstancesCount} /></InspectorFieldRow> : null}
    {missing?.tools.length ? <InspectorFieldRow label="Не найдены операции"><InspectorTextBlock text={missing.tools.join('\n')} /></InspectorFieldRow> : null}
    {missing?.collections.length ? <InspectorFieldRow label="Не найдены коллекции"><InspectorTextBlock text={missing.collections.join('\n')} /></InspectorFieldRow> : null}
    {missing?.credentials.length ? <InspectorFieldRow label="Не настроена авторизация"><InspectorTextBlock text={missing.credentials.join('\n')} /></InspectorFieldRow> : null}
    {readiness && status?.tone === 'success' && !missing?.tools.length && !missing?.collections.length && !missing?.credentials.length ? <InspectorFieldRow label="Проверки доступности"><InspectorScalar value="Необходимые операции, коллекции и авторизация отмечены как доступные." /></InspectorFieldRow> : null}
    {route?.proposed ? <InspectorFieldRow label="Предложенный маршрут"><InspectorScalar value={route.proposed} /></InspectorFieldRow> : null}
    {route?.effective ? <InspectorFieldRow label="Эффективный маршрут"><InspectorScalar value={route.effective} /></InspectorFieldRow> : null}
    {route?.policyDisposition ? <InspectorFieldRow label="Рекомендация политики"><InspectorScalar value={policyDispositionLabels[route.policyDisposition] ?? route.policyDisposition} /></InspectorFieldRow> : null}
    {route?.policyReasonCode ? <InspectorFieldRow label="Код решения"><InspectorScalar value={route.policyReasonCode} /></InspectorFieldRow> : null}
    {route?.reason ? <InspectorFieldRow label="Основание"><InspectorScalar value={({ model_selected: 'Выбор модели', runtime_reroute: 'Перенаправлено приложением', policy_route: 'Маршрут по политике' } as Record<string, string>)[route.reason] ?? route.reason} /></InspectorFieldRow> : null}
    {route?.detail ? <InspectorFieldRow label="Почему изменён"><InspectorTextBlock text={route.detail} /></InspectorFieldRow> : null}
    {route?.goal ? <InspectorFieldRow label="Цель"><InspectorTextBlock text={route.goal} /></InspectorFieldRow> : null}
    {route?.direction ? <InspectorFieldRow label="Направление"><InspectorTextBlock text={route.direction} /></InspectorFieldRow> : null}
    {route?.expectedResult ? <InspectorFieldRow label="Ожидаемый результат"><InspectorTextBlock text={route.expectedResult} /></InspectorFieldRow> : null}
    {route ? <>
      <InspectorFieldRow label="Сущности"><InspectorTextBlock text={list(route.entityHints)} /></InspectorFieldRow>
      <InspectorFieldRow label="Проекты"><InspectorTextBlock text={list(route.projectHints)} /></InspectorFieldRow>
      <InspectorFieldRow label="Ограничения"><InspectorTextBlock text={list(route.constraints)} /></InspectorFieldRow>
      {route.input !== undefined ? <InspectorFieldRow label="Входные данные"><InspectorJsonBlock value={route.input} /></InspectorFieldRow> : null}
    </> : null}
  </InspectorFieldGroup>;
}
