import { useState } from 'react';
import { Badge, Button, Modal } from '@/shared/ui';
import type { MemoryScopeProposalAdminItem } from '@/shared/api/admin';
import { scopeStatusLabels, scopeTypeLabels } from './MemoryScopeTable';
import styles from './MemoryReviewDialog.module.css';

type Props = {
  proposal: MemoryScopeProposalAdminItem;
  pending: boolean;
  onClose: () => void;
  onApprove: (reason?: string) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
};

export default function MemoryScopeProposalDialog({ proposal, pending, onClose, onApprove, onReject }: Props) {
  const [reason, setReason] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState('');
  const reject = async () => {
    if (!reason.trim()) { setError('Укажите причину отклонения.'); return; }
    try { await onReject(reason.trim()); }
    catch (value) { setError(value instanceof Error ? value.message : 'Не удалось отклонить скоуп'); }
  };
  const blocked = proposal.approval_blockers.length > 0 || proposal.status !== 'needs_review';
  return <Modal open title="Проверка скоупа" onClose={onClose} size="md" bodyClassName={styles.body}
    footer={<><Button variant="outline" onClick={onClose}>Закрыть</Button>
      {rejecting ? <><Button variant="outline" disabled={pending} onClick={() => { setRejecting(false); setError(''); }}>Назад</Button>
        <Button variant="danger" disabled={pending || !reason.trim()} onClick={reject}>Отклонить</Button></>
        : <><Button variant="danger" disabled={pending} onClick={() => setRejecting(true)}>Отклонить</Button>
          <Button disabled={pending || blocked} onClick={async () => { try { await onApprove(); } catch (value) { setError(value instanceof Error ? value.message : 'Не удалось утвердить скоуп'); } }}>Утвердить скоуп</Button></>}</>}>
    <div className={styles.layout}>
      <header className={styles.intro}><div className={styles.eyebrow}><Badge tone="info">{scopeTypeLabels[proposal.scope_type]}</Badge><Badge tone={proposal.status === 'needs_review' ? 'warn' : 'neutral'}>{scopeStatusLabels[proposal.status]}</Badge></div>
        <h2>{proposal.name}</h2><p><code>{proposal.proposed_key}</code></p></header>
      <section className={styles.section}><h3>Связанный термин</h3><p>{proposal.term_name || 'Не найден'}</p>
        {proposal.approval_blockers.map((blocker) => <p key={blocker} role="alert">{blocker}</p>)}
      </section>
      <section className={styles.section}><h3>Алиасы</h3><p>{proposal.aliases.join(', ') || '—'}</p><h3>Обоснование</h3><p>{proposal.rationale || '—'}</p>
        <p>Фрагменты источника: {proposal.evidence_section_ids.join(', ') || '—'}</p>
        <p>Зависимых утверждений памяти: {proposal.dependent_candidate_ids.length}</p>
      </section>
      {rejecting && <label className={styles.field}><span>Причина отклонения *</span><textarea rows={3} maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
      {error && <div className={styles.warning} role="alert">{error}</div>}
    </div>
  </Modal>;
}
