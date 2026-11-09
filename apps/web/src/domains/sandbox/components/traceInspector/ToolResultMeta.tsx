import {
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorStatus,
} from '@/shared/ui/Inspector';
import type { TraceToolResult } from '../../traceProjection';
import { InspectorSection } from './InspectorPrimitives';

type Tone = 'neutral' | 'success' | 'warn' | 'danger';

function countTone(
  count: number,
  total: number | undefined,
  complete?: boolean
): Tone {
  if (total === undefined) return 'neutral';
  if (count === 0 && total > 0) return 'danger';
  if (count > total) return 'neutral';
  if (count < total || complete === false) return 'warn';
  return 'success';
}

const number = (value: number) => new Intl.NumberFormat('ru-RU').format(value);

export function ToolResultMeta({
  result,
  storedCount,
  sourceTotal,
  sourceComplete,
  inlineResult = false,
}: {
  result: TraceToolResult;
  storedCount?: number;
  sourceTotal?: number;
  sourceComplete?: boolean;
  inlineResult?: boolean;
}) {
  const isStored = result.delivery === 'stored';
  const total = sourceTotal ?? result.sourceTotal;
  const complete = sourceComplete ?? result.sourceComplete;
  const received =
    result.receivedCount ?? (!isStored ? result.returnedCount : undefined);
  const saved = isStored ? (storedCount ?? result.returnedCount) : undefined;
  const sourceCount = received ?? saved;
  const hasMeta = sourceCount !== undefined || total !== undefined;
  if (!hasMeta) return null;
  return (
    <InspectorSection title="Мета">
      <InspectorFieldGroup>
        {sourceCount !== undefined ? (
          <InspectorFieldRow
            label={
              received !== undefined
                ? 'Получено из источника'
                : isStored && !inlineResult
                  ? 'В наборе / в источнике'
                  : 'Строк в ответе'
            }
          >
            <InspectorStatus
              label={
                total !== undefined
                  ? `${number(sourceCount)} / ${number(total)}`
                  : number(sourceCount)
              }
              tone={countTone(sourceCount, total, complete)}
            />
          </InspectorFieldRow>
        ) : total !== undefined ? (
          <InspectorFieldRow label="Всего в источнике">
            <InspectorStatus label={number(total)} tone="neutral" />
          </InspectorFieldRow>
        ) : null}
        {isStored && !inlineResult && saved !== undefined ? (
          <InspectorFieldRow label="Сохранено в Store / получено">
            <InspectorStatus
              label={`${number(saved)} / ${received !== undefined ? number(received) : '—'}`}
              tone={countTone(saved, received)}
            />
          </InspectorFieldRow>
        ) : null}
      </InspectorFieldGroup>
    </InspectorSection>
  );
}
