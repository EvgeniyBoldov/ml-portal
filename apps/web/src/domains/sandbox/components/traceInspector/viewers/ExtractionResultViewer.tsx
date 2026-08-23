import { InspectorFieldGroup, InspectorFieldRow, InspectorNotice, InspectorScalar, InspectorStatus, InspectorTextBlock } from '@/shared/ui/Inspector';
import type { TraceExtraction } from '../../../traceProjection';

const tone = (status: string): 'neutral' | 'success' | 'warn' | 'danger' => status === 'completed' ? 'success' : status === 'failed' ? 'danger' : 'warn';
const label = (status: string): string => status === 'completed' ? 'Готово' : status === 'failed' ? 'Ошибка' : 'Выполняется';

export function ExtractionResultViewer({ extraction }: { extraction?: TraceExtraction }) {
  if (!extraction) return null;
  const result = extraction.result;
  return <>
    <InspectorFieldGroup>
      <InspectorFieldRow label="Статус"><InspectorStatus label={label(result.status)} tone={tone(result.status)} /></InspectorFieldRow>
      {result.fileName ? <InspectorFieldRow label="Файл"><InspectorScalar value={result.fileName} /></InspectorFieldRow> : null}
      {result.contentType ? <InspectorFieldRow label="Тип содержимого"><InspectorScalar value={result.contentType} /></InspectorFieldRow> : null}
      {result.format ? <InspectorFieldRow label="Формат"><InspectorScalar value={result.format} /></InspectorFieldRow> : null}
      {result.profile ? <InspectorFieldRow label="Профиль"><InspectorScalar value={result.profile} /></InspectorFieldRow> : null}
      {result.representation ? <InspectorFieldRow label="Представление"><InspectorScalar value={result.representation} /></InspectorFieldRow> : null}
      {result.truncated !== undefined ? <InspectorFieldRow label="Обрезано"><InspectorScalar value={result.truncated ? 'Да' : 'Нет'} /></InspectorFieldRow> : null}
      {result.message ? <InspectorFieldRow label="Сообщение"><InspectorTextBlock text={result.message} /></InspectorFieldRow> : null}
      {result.warnings.length ? <InspectorFieldRow label="Предупреждения"><InspectorTextBlock text={result.warnings.join('\n')} /></InspectorFieldRow> : null}
    </InspectorFieldGroup>
    {!result.fileName && !result.contentType && !result.format && !result.message && !result.warnings.length ? <InspectorNotice tone="neutral" message="Извлечение завершилось без дополнительных метаданных." /> : null}
  </>;
}
