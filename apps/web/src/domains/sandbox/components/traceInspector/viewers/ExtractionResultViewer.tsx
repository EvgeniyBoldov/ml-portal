import { InspectorFieldGroup, InspectorFieldRow, InspectorJsonBlock, InspectorNotice, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceExtraction } from '../../../traceProjection';
import { formatFieldLabel } from '../../../callInspection';

const asRecord = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const display = (value: unknown) => typeof value === 'string'
  ? value.length > 120 || value.includes('\n') ? <InspectorTextBlock text={value} /> : <InspectorScalar value={value} />
  : value === null || ['number', 'boolean'].includes(typeof value) ? <InspectorScalar value={value as number | boolean | null} />
  : <InspectorJsonBlock value={value} />;

/** Summarises the extraction child entity of a file-reading tool call. */
export function ExtractionResultViewer({ extraction }: { extraction?: TraceExtraction }) {
  if (!extraction) return null;
  const payload = asRecord(extraction.end?.payload ?? extraction.start?.payload);
  const failed = extraction.entity.status === 'failed' || extraction.end?.event_type === 'extraction_failed';
  const usefulKeys = ['file_name', 'content_type', 'format', 'profile', 'representation', 'truncated', 'warnings', 'error', 'message'];
  const values = usefulKeys.filter((key) => payload[key] !== undefined);
  return <>
    <InspectorFieldGroup>
      <InspectorFieldRow label="Статус"><InspectorStatus label={failed ? 'Ошибка' : extraction.end ? 'Готово' : 'Выполняется'} tone={failed ? 'danger' : extraction.end ? 'success' : 'warn'} /></InspectorFieldRow>
      {values.map((key) => <InspectorFieldRow key={key} label={formatFieldLabel(key)}>{display(payload[key])}</InspectorFieldRow>)}
    </InspectorFieldGroup>
    {!values.length ? <InspectorNotice tone="neutral" message="Извлечение завершилось без дополнительных метаданных." /> : null}
  </>;
}
