import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button, Modal, Textarea } from '@/shared/ui';
import { adminApi } from '@/shared/api/admin';
import styles from './MemoryReviewDialog.module.css';

type Props = {
  ids: string[];
  onClose: () => void;
  onRejected: (ids: string[]) => void;
};

export default function MemoryBulkRejectDialog({ ids, onClose, onRejected }: Props) {
  const [remainingIds, setRemainingIds] = useState(ids);
  const [reason, setReason] = useState('');
  const [completed, setCompleted] = useState(0);
  const [error, setError] = useState('');
  const rejection = useMutation({
    mutationFn: async () => {
      const rejected: string[] = [];
      const failed: string[] = [];
      let firstError = '';
      // Decisions on the same document acquire a snapshot lock. Send them in
      // order, and preserve failed IDs so a partial batch can be retried.
      for (const id of remainingIds) {
        try {
          await adminApi.rejectShadowMemoryCandidate(id, reason.trim());
          rejected.push(id);
        } catch (value) {
          failed.push(id);
          firstError ||= value instanceof Error ? value.message : 'Не удалось отклонить кандидата';
        }
        setCompleted(rejected.length + failed.length);
      }
      return { rejected, failed, firstError };
    },
    onSuccess: ({ rejected, failed, firstError }) => {
      onRejected(rejected);
      if (!failed.length) onClose();
      else {
        setRemainingIds(failed);
        setError(`Отклонено: ${rejected.length}. Не удалось отклонить: ${failed.length}. ${firstError} Повторная отправка обработает только оставшихся кандидатов.`);
      }
    },
  });

  return <Modal open title={`Отклонить кандидатов (${remainingIds.length})`} size="md" bodyClassName={styles.body}
    onClose={() => { if (!rejection.isPending) onClose(); }}
    footer={<><Button variant="outline" disabled={rejection.isPending} onClick={onClose}>Отмена</Button>
      <Button variant="danger" disabled={rejection.isPending || !reason.trim() || !remainingIds.length}
        onClick={() => { setCompleted(0); setError(''); rejection.mutate(); }}>
        {rejection.isPending ? `Обработано ${completed} из ${remainingIds.length}…` : `Отклонить (${remainingIds.length})`}
      </Button></>}>
    <div className={styles.layout}>
      <p>Причина будет сохранена для каждого выбранного кандидата и передана агенту при повторном извлечении документа.</p>
      <label className={styles.field} htmlFor="bulk-memory-rejection-reason">Причина отклонения *
        <Textarea id="bulk-memory-rejection-reason" rows={4} maxLength={2000} value={reason} disabled={rejection.isPending}
          onChange={(event) => setReason(event.target.value)} />
      </label>
      {error && <div className={styles.warning} role="alert">{error}</div>}
    </div>
  </Modal>;
}
