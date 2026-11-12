import { useState } from 'react';
import { SmartViewerModal } from '@/shared/ui/SmartViewer';
import {
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorScalar,
} from '@/shared/ui/Inspector';
import type { TraceToolResult } from '@/domains/sandbox/traceProjection';
import { InspectorEmptyState, InspectorSection } from './InspectorPrimitives';
import {
  presentToolData,
  toolDataLabel,
  toolDataValuePreview,
} from '@/domains/sandbox/toolDataPresentation';
import styles from './ToolDataViewer.module.css';

function formatCount(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}

function coverageText(shown: number, available?: number): string {
  const shownText = `Показано ${formatCount(shown)}`;
  const availableText =
    available === undefined ? '' : ` из ${formatCount(available)} доступных`;
  return `${shownText}${availableText}.`;
}

export function ToolDataViewer({ result }: { result: TraceToolResult }) {
  const [isFullOpen, setIsFullOpen] = useState(false);
  const presentation = presentToolData(result.data, {
    delivery: result.delivery,
    resultId: result.resultId,
    returnedCount: result.returnedCount,
    sourceTotal: result.sourceTotal,
    truncated: result.truncated,
  });
  const isStoredDescriptor =
    result.storedDescriptor === true || presentation.kind === 'descriptor';
  const modalValue =
    presentation.kind === 'descriptor'
      ? { summary: 'Результат сохранён отдельно', counts: presentation.counts }
      : isStoredDescriptor
        ? { summary: 'Результат сохранён отдельно' }
        : result.data;
  const modalTitle = isStoredDescriptor
    ? 'Сведения о результате'
    : 'Доступный результат инструмента';
  const canOpenFull = result.data !== undefined;
  const fullButton = canOpenFull ? (
    <button
      type="button"
      className={styles.fullButton}
      onClick={() => setIsFullOpen(true)}
    >
      {isStoredDescriptor
        ? 'Показать сведения о результате'
        : 'Открыть доступный результат'}
    </button>
  ) : null;

  let content;
  if (result.directRecovery) {
    content = (
      <InspectorSection title="Результат сохранён отдельно">
        <p className={styles.coverage}>
          {result.directRecovery.recoverability === 'reauthorize_and_read_again'
            ? 'Для чтения нужен новый вызов с повторной проверкой доступа.'
            : 'Прочитайте сохранённый результат через действие result.read.'}
        </p>
        {result.directRecovery.resultId ? (
          <InspectorFieldGroup>
            <InspectorFieldRow label="Идентификатор результата">
              <InspectorScalar value={result.directRecovery.resultId} />
            </InspectorFieldRow>
            {result.directRecovery.revision !== undefined ? (
              <InspectorFieldRow label="Версия">
                <InspectorScalar value={result.directRecovery.revision} />
              </InspectorFieldRow>
            ) : null}
          </InspectorFieldGroup>
        ) : null}
      </InspectorSection>
    );
  } else if (presentation.kind === 'empty') {
    content = (
      <InspectorEmptyState
        message={
          result.success === false
            ? (result.message ?? 'Результат не получен.')
            : result.success === true
              ? 'Операция выполнена без данных.'
              : 'Подтверждённых данных нет.'
        }
      />
    );
  } else if (presentation.kind === 'text') {
    content = (
      <pre className={styles.fallback}>
        {toolDataValuePreview(presentation.text)}
      </pre>
    );
  } else if (presentation.kind === 'records') {
    const labels = presentation.columns;
    const metadataEntries = Object.entries(presentation.pageMetadata ?? {})
      .filter(([key]) => !(result.sourceTotal !== undefined && ['total', 'count', 'source_total'].includes(key))
        && !(result.sourceComplete !== undefined && ['complete', 'source_complete'].includes(key))
        && !(result.returnedCount !== undefined && ['returned_count', 'row_count'].includes(key))
        && !(result.queryComplete !== undefined && key === 'query_complete')
        && !(result.truncated && key === 'truncated'))
      .slice(0, 6);
    content = (
      <>
        {metadataEntries.length > 0 ? (
          <InspectorFieldGroup>
            {metadataEntries.map(([key, value]) => (
                <InspectorFieldRow key={key} label={toolDataLabel(key)}>
                  <InspectorScalar
                    value={
                      typeof value === 'string' ||
                      typeof value === 'number' ||
                      typeof value === 'boolean'
                        ? value
                        : toolDataValuePreview(value)
                    }
                  />
                </InspectorFieldRow>
              ))}
          </InspectorFieldGroup>
        ) : null}
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                {labels.map(key => (
                  <th key={key}>{toolDataLabel(key)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {presentation.rows.map((row, index) => (
                <tr key={index}>
                  {labels.map(key => (
                    <td key={key}>{toolDataValuePreview(row[key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.coverage}>
          {coverageText(presentation.shown, presentation.available)}
        </p>
      </>
    );
  } else if (presentation.kind === 'scalars') {
    content = (
      <>
        <ol className={styles.scalarList}>
          {presentation.values.map((value, index) => (
            <li key={index}>{toolDataValuePreview(value)}</li>
          ))}
        </ol>
        <p className={styles.coverage}>
          {coverageText(presentation.shown, presentation.available)}
        </p>
      </>
    );
  } else if (presentation.kind === 'descriptor') {
    content = (
      <div className={styles.descriptor}>
        {presentation.counts.length ? (
          <InspectorFieldGroup>
            {presentation.counts.map(count => (
              <InspectorFieldRow key={count.label} label={count.label}>
                <InspectorScalar value={count.value} />
              </InspectorFieldRow>
            ))}
          </InspectorFieldGroup>
        ) : null}
        <p className={styles.coverage}>
          Полные данные не входят в событие трассы.
        </p>
      </div>
    );
  } else if (presentation.kind === 'record') {
    content = (
      <InspectorFieldGroup>
        {presentation.entries.map(entry => (
          <InspectorFieldRow key={entry.key} label={entry.label}>
            <InspectorScalar
              value={
                typeof entry.value === 'string' ||
                typeof entry.value === 'number' ||
                typeof entry.value === 'boolean' ||
                entry.value === null
                  ? entry.value
                  : toolDataValuePreview(entry.value)
              }
            />
          </InspectorFieldRow>
        ))}
      </InspectorFieldGroup>
    );
  } else {
    content = (
      <InspectorSection title="Содержимое результата">
        <pre className={styles.fallback}>
          {toolDataValuePreview(result.data)}
        </pre>
      </InspectorSection>
    );
  }

  return (
    <div className={styles.root}>
      {content}
      {result.inlineDataContext !== undefined ? (
        <InspectorSection title="Покрытие и предупреждения модели">
          <pre className={styles.fallback}>{toolDataValuePreview(result.inlineDataContext)}</pre>
        </InspectorSection>
      ) : null}
      {result.inlineComplete === false && result.inlineDataAvailable ? (
        <p className={styles.coverage}>Модель получила только представленный фрагмент результата.</p>
      ) : null}
      {fullButton}
      <SmartViewerModal
        value={modalValue}
        open={isFullOpen}
        onClose={() => setIsFullOpen(false)}
        title={modalTitle}
      />
    </div>
  );
}
