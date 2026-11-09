import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@/shared/api/errors';
import { qk } from '@/shared/api/keys';
import Modal from '@/shared/ui/Modal';
import { sandboxApi, type SandboxResultMetadata } from '../../api';
import styles from './StoredResultCard.module.css';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
export function resultCell(value: unknown): string {
  if (value === undefined) return '—';
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (text === undefined) return '—';
  const chars = Array.from(text);
  return chars.length > 300 ? `${chars.slice(0, 300).join('')}…` : text;
}

export function StoredResultModal({
  sessionId,
  runId,
  resultId,
  metadata,
  onClose,
  onRefresh,
}: {
  sessionId: string;
  runId: string;
  resultId: string;
  metadata: SandboxResultMetadata;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [offsets, setOffsets] = useState([0]);
  const offset = offsets[offsets.length - 1];
  const page = useQuery({
    queryKey: qk.sandbox.resultPage(
      sessionId,
      runId,
      resultId,
      offset,
      metadata.revision
    ),
    queryFn: () =>
      sandboxApi.getResultPage(
        sessionId,
        runId,
        resultId,
        offset,
        metadata.revision
      ),
    staleTime: 0,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status < 500) && count < 1,
  });
  const status = page.error instanceof ApiError ? page.error.status : undefined;
  const rows = page.data?.rows ?? [];
  const columns = [
    ...new Set([
      ...Object.keys(metadata.observed_schema),
      ...rows.flatMap(row => (isRecord(row) ? Object.keys(row) : [])),
    ]),
  ];
  const hasScalars = columns.length === 0 || rows.some(row => !isRecord(row));
  const reload = async () => {
    await onRefresh();
    setOffsets([0]);
  };
  return (
    <Modal
      open
      title="Результат инструмента"
      onClose={onClose}
      size="xl"
      className={styles.modalFrame}
      bodyClassName={styles.modalBody}
    >
      <div className={styles.modal}>
        {page.isPending ? (
          <p>Загружаем результат…</p>
        ) : page.isError ? (
          <>
            <p>
              {status === 404
                ? 'Результат больше недоступен.'
                : status === 409
                  ? 'Результат изменился. Загрузите его с начала.'
                  : status === 413
                    ? `Строка ${offset + 1} слишком велика для просмотра.`
                    : 'Не удалось загрузить результат.'}
            </p>
            {status === 409 ? (
              <button type="button" onClick={() => void reload()}>
                Загрузить заново
              </button>
            ) : status !== 404 && status !== 413 ? (
              <button type="button" onClick={() => void page.refetch()}>
                Повторить
              </button>
            ) : null}
          </>
        ) : rows.length === 0 ? (
          <p>В результате нет строк.</p>
        ) : (
          <>
            <div
              className={styles.tableWrap}
              role="region"
              aria-label="Таблица результата"
              tabIndex={0}
            >
              <table className={styles.table}>
                <thead>
                  <tr>
                    {columns.map(column => (
                      <th key={column}>{column}</th>
                    ))}
                    {hasScalars ? <th>Значение</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={offset + index}>
                      {columns.map(column => (
                        <td key={column}>
                          {resultCell(isRecord(row) ? row[column] : undefined)}
                        </td>
                      ))}
                      {hasScalars ? (
                        <td>
                          {resultCell(
                            isRecord(row) && columns.length ? undefined : row
                          )}
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Строки {offset + 1}–{offset + rows.length} из{' '}
              {page.data?.row_count}
            </p>
            <div className={styles.pagination}>
              <button
                type="button"
                disabled={offsets.length === 1 || page.isFetching}
                onClick={() => setOffsets(current => current.slice(0, -1))}
              >
                Назад
              </button>
              <button
                type="button"
                disabled={page.data?.next_offset == null || page.isFetching}
                onClick={() => {
                  if (page.data?.next_offset != null)
                    setOffsets(current => [
                      ...current,
                      page.data!.next_offset!,
                    ]);
                }}
              >
                Далее
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
