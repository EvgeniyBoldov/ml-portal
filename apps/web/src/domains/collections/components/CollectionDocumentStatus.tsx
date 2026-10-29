import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  collectionsApi,
  type Collection,
  type CollectionDocument,
} from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import Modal from '@/shared/ui/Modal';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import Button from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/Toast';
import styles from './CollectionDocumentStatus.module.css';

type Control = {
  stage: string;
  can_retry?: boolean;
  can_stop?: boolean;
  status?: string;
};
const stateLabels: Record<string, string> = {
  ready: 'Готов',
  done: 'Готов',
  completed: 'Готов',
  processing: 'В обработке',
  running: 'В обработке',
  queued: 'В очереди',
  pending: 'Ожидает',
  uploaded: 'Загружен',
  failed: 'Ошибка',
  error: 'Ошибка',
  cancelled: 'Остановлен',
  skipped: 'Пропущен',
};
function stageLabel(stage: string) {
  if (stage.startsWith('embed.')) return 'Векторизация';
  if (stage.startsWith('index.')) return 'Индексация';
  return (
    {
      pipeline: 'Обработка документа',
      extract: 'Извлечение текста',
      normalize: 'Подготовка текста',
      chunk: 'Разбиение текста',
    } as Record<string, string>
  )[stage];
}
export default function CollectionDocumentStatus({
  collection,
  document,
  onClose,
  onChanged,
}: {
  collection: Collection;
  document?: CollectionDocument;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const [busy, setBusy] = useState(false);
  const [confirmMemoryDelete, setConfirmMemoryDelete] = useState(false);
  const status = useQuery({
    queryKey: qk.collections.documentGraph(collection.id, document?.id || ''),
    queryFn: () =>
      collectionsApi.getDocStatusGraph(collection.id, document!.id),
    enabled: !!document,
    refetchInterval: 5000,
  });
  const graph = status.data as
    | { ingest_policy?: { controls?: Control[]; start_allowed?: boolean } }
    | undefined;
  const controls = (graph?.ingest_policy?.controls || []).filter(control =>
    stageLabel(control.stage)
  );
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
      showToast('Действие принято', 'success');
      onChanged();
      void status.refetch();
    } catch {
      showToast(
        'Действие недоступно или не выполнено. Обновите статус и попробуйте снова.',
        'error'
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={!!document}
      title={document?.name || document?.filename || 'Статус документа'}
      onClose={onClose}
    >
      {status.isError ? (
        <div role="alert">
          Не удалось загрузить статус.{' '}
          <Button variant="ghost" onClick={() => void status.refetch()}>
            Повторить
          </Button>
        </div>
      ) : (
        <div className={styles.content}>
          <p>
            Обработка RAG:{' '}
            {stateLabels[document?.agg_status || ''] || 'Статус уточняется'}
          </p>
          {status.isLoading && <p role="status">Загрузка этапов обработки…</p>}
          {controls.map(control => (
            <div key={control.stage} className={styles.stage}>
              <span>{stageLabel(control.stage)}</span>
              <span>
                {stateLabels[control.status || ''] || 'Статус уточняется'}
              </span>
              {collection.capabilities?.ingest && (
                <div className={styles.actions}>
                  {control.can_retry && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(() =>
                          collectionsApi.retryDocIngest(
                            collection.id,
                            document!.id,
                            control.stage
                          )
                        )
                      }
                    >
                      Повторить этап
                    </Button>
                  )}
                  {control.can_stop && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(() =>
                          collectionsApi.stopDocIngest(
                            collection.id,
                            document!.id,
                            control.stage
                          )
                        )
                      }
                    >
                      Остановить этап
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
          {collection.capabilities?.ingest &&
            graph?.ingest_policy?.start_allowed && (
              <Button
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    collectionsApi.startDocIngest(collection.id, document!.id)
                  )
                }
              >
                Запустить обработку
              </Button>
            )}
          {collection.capabilities?.manage_memory && (
            <section className={styles.content}>
              <h3>LongMemory</h3>
              <p>Добавление и удаление из памяти не заменяют обработку RAG.</p>
              <div className={styles.actions}>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      collectionsApi.addDocumentToMemory(
                        collection.id,
                        document!.id
                      )
                    )
                  }
                >
                  Добавить в LongMemory
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setConfirmMemoryDelete(true)}
                >
                  Удалить из LongMemory
                </Button>
              </div>
            </section>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirmMemoryDelete}
        title="Удалить из LongMemory?"
        message={`Документ «${document?.name || document?.filename || ''}» будет исключён из памяти. Оригинал и данные RAG останутся в коллекции.`}
        confirmLabel="Удалить из LongMemory"
        onConfirm={() => {
          setConfirmMemoryDelete(false);
          void run(() =>
            collectionsApi.removeDocumentFromMemory(collection.id, document!.id)
          );
        }}
        onCancel={() => setConfirmMemoryDelete(false)}
      />
    </Modal>
  );
}
