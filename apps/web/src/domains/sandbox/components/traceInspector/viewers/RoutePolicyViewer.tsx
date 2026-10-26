import {
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorScalar,
  InspectorTextBlock,
} from '@/shared/ui/Inspector';
import type { TraceRoutePolicy } from '@domains/sandbox/traceProjection';
import { InspectorEmptyState } from '../InspectorPrimitives';

const signalLabels: Record<string, string> = {
  inventory_source_mentioned: 'Упомянут источник инвентаря',
  current_records_requested: 'Запрошены текущие записи',
  inventory_agent_available: 'Агент инвентаря доступен',
  documentation_request: 'Запрос о документации',
};

const routeLabels: Record<string, string> = {
  planner: 'Планер',
  synthesis: 'Синтезатор',
  tool_call: 'Вызов инструмента',
};

export function RoutePolicyViewer({
  decision,
}: {
  decision?: TraceRoutePolicy;
}) {
  if (!decision)
    return (
      <InspectorEmptyState message="Решение политики маршрутизации не записано." />
    );
  const isRecommendation = decision.status !== undefined;
  const status = isRecommendation
    ? decision.status === 'matched' ? 'Найдены подходящие сигналы' : 'Подходящих сигналов нет'
    : decision.matched ? 'Историческое правило сработало' : 'Историческое правило не совпало';
  return (
    <InspectorFieldGroup>
      <InspectorFieldRow label={isRecommendation ? 'Рекомендация' : 'Историческое решение'}>
        <InspectorScalar value={status} />
      </InspectorFieldRow>
      {decision.routeHint ? <InspectorFieldRow label="Подсказка маршрута">
        <InspectorScalar value={routeLabels[decision.routeHint] ?? decision.routeHint} />
      </InspectorFieldRow> : null}
      {!isRecommendation && decision.route ? <InspectorFieldRow label="Исторический маршрут">
        <InspectorScalar value={routeLabels[decision.route] ?? decision.route} />
      </InspectorFieldRow> : null}
      {decision.recommendationId ? <InspectorFieldRow label="ID рекомендации">
        <InspectorScalar value={decision.recommendationId} />
      </InspectorFieldRow> : null}
      {decision.ruleId ? (
        <InspectorFieldRow label="Правило">
          <InspectorScalar value={decision.ruleId} />
        </InspectorFieldRow>
      ) : null}
      {decision.sourceAgent ? (
        <InspectorFieldRow label="Кандидат источника">
          <InspectorScalar value={decision.sourceAgent} />
        </InspectorFieldRow>
      ) : null}
      {decision.reasonCode ? <InspectorFieldRow label="Код основания">
        <InspectorScalar value={decision.reasonCode} />
      </InspectorFieldRow> : null}
      {(decision.summary ?? decision.detail) ? <InspectorFieldRow label="Основание">
        <InspectorTextBlock text={decision.summary ?? decision.detail ?? ''} />
      </InspectorFieldRow> : null}
      {decision.signals.length ? (
        <InspectorFieldRow label="Проверенные условия">
          <InspectorTextBlock
            text={decision.signals
              .map(signal => signalLabels[signal] ?? signal)
              .join('\n')}
          />
        </InspectorFieldRow>
      ) : null}
      {!isRecommendation && decision.userRequest ? (
        <InspectorFieldRow label="Запрос">
          <InspectorTextBlock text={decision.userRequest} />
        </InspectorFieldRow>
      ) : null}
    </InspectorFieldGroup>
  );
}
