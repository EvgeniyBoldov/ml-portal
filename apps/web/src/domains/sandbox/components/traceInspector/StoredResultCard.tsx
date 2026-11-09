import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@/shared/api/errors';
import { qk } from '@/shared/api/keys';
import Modal from '@/shared/ui/Modal';
import {
  InspectorFieldGroup,
  InspectorFieldRow,
  InspectorScalar,
} from '@/shared/ui/Inspector';
import { sandboxApi } from '../../api';
import type { TraceToolResult } from '../../traceProjection';
import { InspectorSection } from './InspectorPrimitives';
import { StoredResultModal } from './StoredResultModal';
import { ToolResultMeta } from './ToolResultMeta';
import styles from './StoredResultCard.module.css';

export function StoredResultCard({
  sessionId,
  runId,
  resultId,
  traceData,
  returnedCount,
  sourceTotal,
  result,
}: {
  sessionId: string;
  runId: string;
  resultId: string;
  traceData?: unknown;
  returnedCount?: number;
  sourceTotal?: number;
  result?: TraceToolResult;
}) {
  const [open, setOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const metadata = useQuery({
    queryKey: qk.sandbox.resultMetadata(sessionId, runId, resultId),
    queryFn: () => sandboxApi.getResultMetadata(sessionId, runId, resultId),
    staleTime: 0,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status < 500) && count < 1,
    refetchOnMount: 'always',
  });
  const missing =
    metadata.error instanceof ApiError && metadata.error.status === 404;
  const available =
    !metadata.isError &&
    metadata.data &&
    Date.parse(metadata.data.expires_at) > Date.now();
  const expired = !metadata.isError && metadata.data && !available;
  const openResult = async () => {
    const latest = await metadata.refetch();
    if (
      !latest.isError &&
      latest.data &&
      Date.parse(latest.data.expires_at) > Date.now()
    )
      setOpen(true);
  };
  const record =
    traceData && typeof traceData === 'object' && !Array.isArray(traceData)
      ? (traceData as Record<string, unknown>)
      : {};
  const fallback =
    record.observed_schema &&
    typeof record.observed_schema === 'object' &&
    !Array.isArray(record.observed_schema)
      ? (record.observed_schema as Record<string, unknown>)
      : {};
  const schema = metadata.data?.observed_schema ?? fallback;
  const count = !metadata.isError
    ? (metadata.data?.row_count ?? returnedCount)
    : returnedCount;
  const total = !metadata.isError
    ? (metadata.data?.source_total ?? sourceTotal)
    : sourceTotal;
  return (
    <>
      <InspectorSection title="Результат">
        <div className={styles.card}>
          <InspectorFieldGroup>
            <InspectorFieldRow label="ID результата">
              <InspectorScalar value={resultId} />
            </InspectorFieldRow>
          </InspectorFieldGroup>
          {metadata.isPending || metadata.isFetching ? (
            <p>Проверяем доступность результата…</p>
          ) : missing ? (
            <p>Результат больше недоступен.</p>
          ) : expired ? (
            <p>Срок хранения истёк. Получить результат нельзя.</p>
          ) : metadata.isError ? (
            <>
              <p>Не удалось проверить доступность результата.</p>
              <button type="button" onClick={() => void metadata.refetch()}>
                Повторить
              </button>
            </>
          ) : null}
          <div className={styles.actions}>
            <button
              type="button"
              disabled={!available || metadata.isFetching}
              onClick={() => void openResult()}
            >
              Показать результат в Store
            </button>
            <button
              type="button"
              disabled={!Object.keys(schema).length}
              onClick={() => setSchemaOpen(true)}
            >
              Показать схему
            </button>
          </div>
          {schemaOpen ? (
            <Modal
              open
              title="Схема результата"
              onClose={() => setSchemaOpen(false)}
              size="lg"
              className={styles.modalFrame}
              bodyClassName={styles.modalBody}
            >
              <ul className={styles.schemaList}>
                {Object.entries(schema).map(([name, value]) => (
                  <li key={name}>
                    <strong>{name}</strong>
                    {value &&
                    typeof value === 'object' &&
                    'types' in value &&
                    Array.isArray(value.types)
                      ? ` — ${value.types.join(', ')}`
                      : ''}
                  </li>
                ))}
              </ul>
            </Modal>
          ) : null}
          {open && metadata.data ? (
            <StoredResultModal
              sessionId={sessionId}
              runId={runId}
              resultId={resultId}
              metadata={metadata.data}
              onClose={() => setOpen(false)}
              onRefresh={async () => {
                await metadata.refetch();
              }}
            />
          ) : null}
        </div>
      </InspectorSection>
      {result ? (
        <ToolResultMeta
          result={result}
          storedCount={count}
          sourceTotal={total ?? undefined}
          sourceComplete={
            !metadata.isError ? metadata.data?.source_complete : undefined
          }
        />
      ) : null}
    </>
  );
}
