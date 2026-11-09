import Badge from '@/shared/ui/Badge';
import { InspectorSection, InspectorStack } from '../InspectorPrimitives';
import type { TraceAgentResponseView } from '../../../traceProjection';
import { AgentDiagnostics, AgentFiles, AgentNeeds, AgentSources } from './AgentResultDetails';
import { AgentStructuredData } from './AgentStructuredData';
import styles from './AgentResultViewer.module.css';

const TEXT_PREVIEW_LIMIT = 800;

function ResultText({ text }: { text: string }) {
  if (text.length <= TEXT_PREVIEW_LIMIT) return <p className={styles.answer}>{text}</p>;
  return <div className={styles.longText}>
    <p className={styles.answer}>{text.slice(0, TEXT_PREVIEW_LIMIT)}…</p>
    <details><summary>Показать весь текст</summary><p className={styles.answer}>{text}</p></details>
  </div>;
}

export function AgentResultViewer({ response }: { response: TraceAgentResponseView }) {
  const hasInteraction = Boolean(response.interaction?.question || response.interaction?.message
    || response.interaction?.responseTypeLabel || response.interaction?.options.length);
  const missingInputs = response.missingInputs;
  const hasMissingInputs = missingInputs !== undefined && missingInputs !== null
    && !(Array.isArray(missingInputs) && missingInputs.length === 0)
    && !(typeof missingInputs === 'object' && !Array.isArray(missingInputs) && Object.keys(missingInputs).length === 0);
  const hasNeeds = response.needs.length > 0;
  const hasCompletionContext = response.completion === 'needs' || response.completion === 'unfulfillable'
    || response.outcome === 'needs_dependency' || response.outcome === 'unfulfillable';
  const hasAnyData = Boolean(response.answer || response.failureMessage || response.hasStructuredData || hasInteraction || hasCompletionContext
    || hasNeeds || response.limitation || response.sufficientForPhase !== undefined || hasMissingInputs
    || response.artifacts.length || response.sources.length || response.diagnostics.length);
  if (!hasAnyData) return <div className={styles.empty}>Исполнитель не записал содержательный результат.</div>;

  const showInsufficient = response.sufficientForPhase === false;
  const showNeedsFallback = (response.completion === 'needs' || response.outcome === 'needs_dependency')
    && !hasNeeds && !hasMissingInputs;
  const showUnfulfillableFallback = (response.outcome === 'unfulfillable' || response.completion === 'unfulfillable') && !response.limitation;
  const duplicateLimitation = Boolean(response.failureMessage && response.limitation?.message === response.failureMessage);

  return <InspectorStack>
    {response.answer ? <InspectorSection title="Ответ"><ResultText text={response.answer} /></InspectorSection> : null}
    {response.failureMessage ? <InspectorSection title="Проблема">
      <ResultText text={response.failureMessage} />
      {duplicateLimitation && response.limitation?.actionLabel ? <Badge size="small" tone="warn">{response.limitation.actionLabel}</Badge> : null}
    </InspectorSection> : null}
    {hasInteraction && response.interaction ? <InspectorSection title={response.interaction.kind === 'confirmation' ? 'Требуется подтверждение' : 'Нужно уточнение'}>
      {response.interaction.question ? <p className={styles.answer}>{response.interaction.question}</p> : null}
      {response.interaction.message && response.interaction.message !== response.interaction.question
        ? <p className={styles.secondary}>{response.interaction.message}</p> : null}
      {response.interaction.responseTypeLabel ? <p className={styles.secondary}>Формат ответа: {response.interaction.responseTypeLabel}</p> : null}
      {response.interaction.options.length ? <>
        <ul className={styles.options}>{response.interaction.options.slice(0, 10).map((option, index) => <li key={`${option}:${index}`}>{option}</li>)}</ul>
        {response.interaction.options.length > 10 ? <details className={styles.moreOptions}>
          <summary>Показать ещё {response.interaction.options.length - 10}</summary>
          <ul className={styles.options}>{response.interaction.options.slice(10).map((option, index) => <li key={`${option}:${index + 10}`}>{option}</li>)}</ul>
        </details> : null}
      </> : null}
    </InspectorSection> : null}
    {hasNeeds ? <AgentNeeds items={response.needs} /> : null}
    {hasMissingInputs && !hasNeeds
      ? <AgentStructuredData value={missingInputs} title="Недостающие данные" /> : null}
    {response.hasStructuredData ? <AgentStructuredData value={response.structuredData} /> : null}
    <AgentFiles items={response.artifacts} />
    <AgentSources items={response.sources} />
    {response.limitation && !duplicateLimitation ? <InspectorSection title="Ограничение">
      <p className={styles.answer}>{response.limitation.message}</p>
      {response.limitation.actionLabel ? <Badge size="small" tone="warn">{response.limitation.actionLabel}</Badge> : null}
    </InspectorSection> : null}
    {showNeedsFallback ? <InspectorSection title="Продолжение"><p className={styles.secondary}>Для продолжения нужны дополнительные данные; их перечень не записан.</p></InspectorSection> : null}
    {showUnfulfillableFallback ? <InspectorSection title="Итог"><p className={styles.secondary}>Исполнитель сообщил, что выполнить задачу не удалось.</p></InspectorSection> : null}
    {response.sufficientForPhase !== undefined ? <InspectorSection title="Оценка следующего шага"><p className={styles.secondary}>
      {showInsufficient ? 'Записанного результата недостаточно для следующего этапа.' : 'Записанного результата достаточно для следующего этапа.'}
    </p></InspectorSection> : null}
    <AgentDiagnostics items={response.diagnostics} />
  </InspectorStack>;
}
