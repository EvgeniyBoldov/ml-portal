import { InspectorFieldGroup, InspectorFieldRow, InspectorScalar, InspectorStatus } from '@/shared/ui/Inspector';
import type { TraceMemoryComponentResult } from '../../../traceProjection';
import { InspectorEmptyState, InspectorSection, InspectorStack } from '../InspectorPrimitives';

const statusLabel = (status: string | undefined): string => ({ pending: 'Кандидат', confirmed: 'Подтверждён', unconfirmed: 'Не подтверждён' })[status ?? ''] ?? status ?? '—';
const changeLabel = (change: string): string => ({
  candidate_extracted: 'Извлечён кандидат',
  candidate_created: 'Создан кандидат',
  candidate_reinforced: 'Добавлено подтверждение',
  candidate_confirmed: 'Кандидат подтверждён',
  confirmed: 'Сразу подтверждён',
  sandbox_updated: 'Обновлён в sandbox',
})[change] ?? change;

const actionLabel = (action: string): string => ({
  add: 'Опубликовать как новое знание', rewrite: 'Обновить формулировку',
  merge: 'Объединить подтверждения', supersede: 'Заменить прежнее знание',
  mark_conflict: 'Отметить конфликт', discard: 'Отклонить',
})[action] ?? action;

const outcomeLabel = (outcome: string): string => ({
  accepted: 'Принят', rejected: 'Отклонён', skipped: 'Пропущен', conflict: 'Конфликт', published: 'Опубликован',
})[outcome] ?? outcome;

const reasonLabel = (reason: string): string => ({
  evidence_validated: 'Evidence подтверждён', limit_exceeded: 'Превышен лимит кандидатов', unknown_scope: 'Неизвестная область',
  empty_content: 'Пустое свойство или значение', missing_owner: 'Не определён владелец области', unsupported_kind: 'Неподдерживаемый тип знания',
  invalid_glossary_scope: 'Недопустимая область термина', below_confidence: 'Недостаточная уверенность', invalid_subject: 'Недопустимое свойство',
  ephemeral_value: 'Нестабильное или временное значение', evidence_not_matched: 'Не найдено подтверждающее evidence',
  user_evidence_required: 'Для персонального факта требуется сообщение пользователя', exact_match: 'Совпадает с известным знанием',
  compactor_fallback: 'Компактор недоступен: сохранён исходный кандидат', invalid_source_indexes: 'Некорректная связь кандидатов',
  discarded_by_compactor: 'Отклонён компактором', compaction_resolved: 'Решение компактора принято',
  unrepresented_passthrough: 'Не вошёл в ответ компактора: сохранён без изменений', no_new_evidence: 'Новых независимых evidence нет',
  candidate_created: 'Создан кандидат', candidate_reinforced: 'Добавлено подтверждение', candidate_confirmed: 'Кандидат подтверждён',
  marked_unconfirmed: 'Помечен как конфликтный', glossary_pending: 'Термин ожидает подтверждений', glossary_confirmed: 'Термин подтверждён',
  sandbox_overlay_updated: 'Обновлён только overlay Sandbox', sandbox_branch_missing: 'Ветка Sandbox не найдена', marked_conflict: 'Помечен как конфликтный',
})[reason] ?? 'Безопасная причина не классифицирована';

const phaseLabel = (phase: string): string => ({
  extraction_validation: 'Проверка извлечения', compaction: 'Компактация', reconciliation: 'Сверка', publication: 'Публикация',
})[phase] ?? 'Обработка памяти';

type FactsMode = 'candidates' | 'decisions' | 'published';

export function FactsViewer({ result, mode }: { result: TraceMemoryComponentResult | undefined; mode: FactsMode }) {
  const isCompactor = result?.componentName === 'fact_compactor';
  const decisions = result?.decisions.filter((item) => (
    mode === 'published' ? item.outcome === 'published' : mode === 'decisions' ? item.outcome !== 'published' : true
  )) ?? [];
  // Component result and decision journal answer different questions. Never
  // hide the persisted result merely because a decision was recorded.
  const legacyFacts = mode === 'published' ? [] : result?.facts ?? [];
  const emptyMessage = mode === 'published'
    ? 'Опубликованных изменений в этом запуске нет.'
    : isCompactor ? 'Решения этого запуска не записаны в журнал.' : 'Кандидаты не извлечены или не прошли проверку evidence.';
  if (!result) return <InspectorEmptyState message={emptyMessage} />;
  return <InspectorStack>
    <InspectorFieldGroup>
      <InspectorFieldRow label="Статус компонента"><InspectorStatus label={result?.status === 'ok' ? 'Завершён' : result?.status === 'degraded' ? 'Завершён с ограничениями' : result?.status ?? '—'} tone={result?.status === 'ok' ? 'success' : result?.status === 'failed' ? 'danger' : 'warn'} /></InspectorFieldRow>
      {result ? <InspectorFieldRow label="Итоги"><InspectorScalar value={`Создано: ${result.insertedCount}; обновлено: ${result.updatedCount}; пропущено: ${result.skippedCount}`} /></InspectorFieldRow> : null}
      {result?.durationMs !== undefined ? <InspectorFieldRow label="Длительность"><InspectorScalar value={`${result.durationMs} мс`} /></InspectorFieldRow> : null}
      {result && Object.keys(result.decisionCounts).length ? <InspectorFieldRow label="Счётчики решений"><InspectorScalar value={Object.entries(result.decisionCounts).map(([key, value]) => `${key}: ${value}`).join(', ')} /></InspectorFieldRow> : null}
      {result?.errorCode ? <InspectorFieldRow label="Код ошибки"><InspectorScalar value={result.errorCode} /></InspectorFieldRow> : null}
      {result?.errorMessage ? <InspectorFieldRow label="Сообщение"><InspectorScalar value={result.errorMessage} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    {!legacyFacts.length && !decisions.length ? <InspectorEmptyState message={emptyMessage} /> : null}
    {decisions.map((decision, index) => <InspectorSection key={`${decision.candidateIds.join(':')}:${index}`} title={`${mode === 'published' ? 'Изменение' : mode === 'candidates' ? 'Кандидат' : 'Решение'} ${index + 1}`}>
    <InspectorFieldGroup>
      <InspectorFieldRow label="Результат"><InspectorStatus label={outcomeLabel(decision.outcome)} tone={decision.outcome === 'published' || decision.outcome === 'accepted' ? 'success' : decision.outcome === 'rejected' || decision.outcome === 'conflict' ? 'warn' : 'neutral'} /></InspectorFieldRow>
      <InspectorFieldRow label="Этап"><InspectorScalar value={phaseLabel(decision.phase)} /></InspectorFieldRow>
      <InspectorFieldRow label="Причина"><InspectorScalar value={reasonLabel(decision.reasonCode)} /></InspectorFieldRow>
      {decision.fact ? <>
        <InspectorFieldRow label="Область"><InspectorScalar value={decision.fact.scope} /></InspectorFieldRow>
        <InspectorFieldRow label="Тип"><InspectorScalar value={decision.fact.kind} /></InspectorFieldRow>
        <InspectorFieldRow label="Свойство"><InspectorScalar value={decision.fact.subject} /></InspectorFieldRow>
        <InspectorFieldRow label="Значение"><InspectorScalar value={decision.fact.value} /></InspectorFieldRow>
      </> : null}
      {decision.action ? <InspectorFieldRow label="Действие"><InspectorScalar value={actionLabel(decision.action)} /></InspectorFieldRow> : null}
      {decision.candidateIds.length ? <InspectorFieldRow label="ID кандидатов"><InspectorScalar value={decision.candidateIds.join(', ')} /></InspectorFieldRow> : null}
      {decision.evidenceCount !== undefined ? <InspectorFieldRow label="Evidence"><InspectorScalar value={decision.evidenceCount} /></InspectorFieldRow> : null}
      {decision.fact?.statusAfter ? <InspectorFieldRow label="Статус"><InspectorScalar value={`${statusLabel(decision.fact.statusBefore)} → ${statusLabel(decision.fact.statusAfter)}`} /></InspectorFieldRow> : null}
      {decision.fact?.supportDelta !== undefined ? <InspectorFieldRow label="Подтверждения"><InspectorScalar value={`${decision.fact.supportDelta >= 0 ? '+' : ''}${decision.fact.supportDelta}${decision.fact.supportBefore !== undefined && decision.fact.supportAfter !== undefined ? `: ${decision.fact.supportBefore} → ${decision.fact.supportAfter}` : ''}`} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    </InspectorSection>)}
  {legacyFacts.map((fact, index) => <InspectorSection key={`${fact.subject}:${fact.value}:${index}`} title={`${isCompactor ? 'Результат' : 'Кандидат'} ${index + 1}`}>
      <InspectorFieldGroup>
        <InspectorFieldRow label="Область"><InspectorScalar value={fact.scope} /></InspectorFieldRow>
        <InspectorFieldRow label="Тип"><InspectorScalar value={fact.kind} /></InspectorFieldRow>
        <InspectorFieldRow label="Свойство"><InspectorScalar value={fact.subject} /></InspectorFieldRow>
        <InspectorFieldRow label="Значение"><InspectorScalar value={fact.value} /></InspectorFieldRow>
        <InspectorFieldRow label="Изменение"><InspectorScalar value={changeLabel(fact.changeType)} /></InspectorFieldRow>
        {fact.statusAfter ? <InspectorFieldRow label="Статус"><InspectorStatus label={fact.statusBefore ? `${statusLabel(fact.statusBefore)} → ${statusLabel(fact.statusAfter)}` : statusLabel(fact.statusAfter)} tone={fact.statusAfter === 'confirmed' ? 'success' : 'warn'} /></InspectorFieldRow> : null}
        {fact.supportDelta !== undefined ? <InspectorFieldRow label="Подтверждения"><InspectorScalar value={fact.supportBefore !== undefined && fact.supportAfter !== undefined ? `${fact.supportDelta >= 0 ? '+' : ''}${fact.supportDelta}: ${fact.supportBefore} → ${fact.supportAfter}` : `${fact.supportDelta >= 0 ? '+' : ''}${fact.supportDelta}`} /></InspectorFieldRow> : null}
        {fact.compactionAction ? <InspectorFieldRow label="Решение"><InspectorScalar value={actionLabel(fact.compactionAction)} /></InspectorFieldRow> : null}
        {fact.decisionReason ? <InspectorFieldRow label="Причина"><InspectorScalar value={fact.decisionReason} /></InspectorFieldRow> : null}
        {fact.confidence !== undefined ? <InspectorFieldRow label="Уверенность"><InspectorScalar value={fact.confidence} /></InspectorFieldRow> : null}
      </InspectorFieldGroup>
    </InspectorSection>)}</InspectorStack>;
}
