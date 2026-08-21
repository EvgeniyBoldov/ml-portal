import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { TraceMemoryComponentResult } from '../../../traceProjection';

const statusLabel = (status: string | undefined): string => ({ pending: 'Кандидат', confirmed: 'Подтверждён', unconfirmed: 'Не подтверждён' })[status ?? ''] ?? status ?? '—';
const changeLabel = (change: string): string => ({
  candidate_extracted: 'Извлечён кандидат',
  candidate_created: 'Создан кандидат',
  candidate_reinforced: 'Добавлено подтверждение',
  candidate_confirmed: 'Кандидат подтверждён',
  confirmed: 'Сразу подтверждён',
  sandbox_updated: 'Обновлён в sandbox',
})[change] ?? change;

export function FactsViewer({ result }: { result: TraceMemoryComponentResult | undefined }) {
  if (!result?.facts.length) return <InspectorNotice tone="neutral" message={result?.componentName === 'fact_compactor' ? 'Изменений фактов в этом запуске нет.' : 'Факты на этом шаге не были извлечены или не прошли проверку.'} />;
  return <div>{result.facts.map((fact, index) => <InspectorFieldGroup key={`${fact.subject}:${fact.value}:${index}`}>
    <InspectorFieldRow label="Область"><InspectorScalar value={fact.scope} /></InspectorFieldRow>
    <InspectorFieldRow label="Свойство"><InspectorScalar value={fact.subject} /></InspectorFieldRow>
    <InspectorFieldRow label="Значение"><InspectorScalar value={fact.value} /></InspectorFieldRow>
    <InspectorFieldRow label="Изменение"><InspectorScalar value={changeLabel(fact.changeType)} /></InspectorFieldRow>
    {fact.statusAfter ? <InspectorFieldRow label="Статус"><InspectorStatus label={fact.statusBefore ? `${statusLabel(fact.statusBefore)} → ${statusLabel(fact.statusAfter)}` : statusLabel(fact.statusAfter)} tone={fact.statusAfter === 'confirmed' ? 'success' : 'warn'} /></InspectorFieldRow> : null}
    {fact.supportDelta !== undefined ? <InspectorFieldRow label="Подтверждения"><InspectorScalar value={fact.supportBefore !== undefined && fact.supportAfter !== undefined ? `+${fact.supportDelta}: ${fact.supportBefore} → ${fact.supportAfter}` : `+${fact.supportDelta}`} /></InspectorFieldRow> : null}
    {fact.compactionAction ? <InspectorFieldRow label="Решение компактора"><InspectorScalar value={fact.compactionAction} /></InspectorFieldRow> : null}
    {fact.confidence !== undefined ? <InspectorFieldRow label="Уверенность"><InspectorScalar value={fact.confidence} /></InspectorFieldRow> : null}
  </InspectorFieldGroup>)}</div>;
}
