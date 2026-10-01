import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge, Button, Modal } from '@/shared/ui';
import { adminApi, type ShadowMemoryCandidate } from '@/shared/api/admin';
import styles from './MemoryReviewDialog.module.css';

export type MemoryApproval = { reason?: string; replace_existing_definition?: boolean };

type Props = {
  candidate: ShadowMemoryCandidate;
  pending: boolean;
  onClose: () => void;
  onApprove: (decision: MemoryApproval) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
};

const labels: Record<string, string> = {
  term: 'Термин', description: 'Описание', relationship: 'Связь', rule: 'Правило',
  constraint: 'Ограничение', procedure: 'Процедура', decision: 'Решение',
};

export default function MemoryReviewDialog({ candidate, pending, onClose, onApprove, onReject }: Props) {
  const evidence = useQuery({ queryKey: ['admin', 'memory', 'candidate-evidence', candidate.id],
    queryFn: () => adminApi.getShadowCandidateEvidence(candidate.id), retry: false });
  const glossary = useQuery({ queryKey: ['admin', 'glossary'], queryFn: () => adminApi.getGlossary(), enabled: candidate.candidate_type === 'term' });
  const published = glossary.data?.find((term) => term.normalized_term === candidate.normalized_subject);
  const definition = String(candidate.content?.definition ?? '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const changedDefinition = Boolean(published && published.definition.trim().replace(/\s+/g, ' ').toLocaleLowerCase() !== definition);
  const [replaceDefinition, setReplaceDefinition] = useState(false);
  const [replaceReason, setReplaceReason] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState('');
  const blocked = candidate.conflict_ids.length > 0 || candidate.approval_blockers.length > 0 || !candidate.content_valid;

  const approve = async () => {
    setError('');
    if (changedDefinition && (!replaceDefinition || !replaceReason.trim())) {
      setError('Подтвердите замену определения и укажите причину.');
      return;
    }
    try { await onApprove(changedDefinition ? { replace_existing_definition: true, reason: replaceReason.trim() } : {}); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось утвердить кандидата'); }
  };
  const reject = async () => {
    if (!rejectReason.trim()) { setError('Укажите причину отклонения.'); return; }
    try { await onReject(rejectReason.trim()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось отклонить кандидата'); }
  };

  return <Modal open title="Проверка памяти" onClose={onClose} size="lg" bodyClassName={styles.body}
    footer={<><Button variant="outline" onClick={onClose}>Закрыть</Button>
      {rejecting ? <><Button variant="outline" disabled={pending} onClick={() => { setRejecting(false); setError(''); }}>Назад</Button>
        <Button variant="danger" disabled={pending || !rejectReason.trim()} onClick={reject}>{pending ? 'Сохраняю…' : 'Отклонить'}</Button></>
        : <><Button variant="danger" disabled={pending} onClick={() => setRejecting(true)}>Отклонить</Button>
          <Button disabled={pending || blocked} onClick={approve}>{pending ? 'Сохраняю…' : 'Утвердить'}</Button></>}</>}>
    <div className={styles.layout}>
      <header className={styles.intro}><div className={styles.eyebrow}><Badge tone="info">{labels[candidate.candidate_type] ?? candidate.candidate_type}</Badge><span>Кандидат из документа</span></div>
        <h2>{candidate.subject}</h2><p>Содержание и связи подготовлены извлечением.</p></header>
      {blocked && <div className={styles.warning} role="alert"><strong>Кандидат пока нельзя утвердить</strong>
        {[...candidate.approval_blockers, ...(candidate.conflict_ids.length ? ['Сначала разрешите конфликт кандидата.'] : []), ...(!candidate.content_valid ? [candidate.content_error ?? 'Содержание не прошло проверку.'] : [])].map((item) => <span key={item}>{item}</span>)}
      </div>}
      {candidate.candidate_type === 'term' && published && <div className={styles.warning}><strong>Действующее определение</strong><span>{published.definition}</span>
        {changedDefinition && <><label className={styles.check}><input type="checkbox" checked={replaceDefinition} onChange={(event) => setReplaceDefinition(event.target.checked)} /> Утвердить замену определения</label>
          {replaceDefinition && <label className={styles.field}><span>Причина замены *</span><textarea rows={2} maxLength={2000} value={replaceReason} onChange={(event) => setReplaceReason(event.target.value)} /></label>}</>}
      </div>}
      <section className={styles.section}><h3>Содержание</h3><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(candidate.content, null, 2)}</pre>
        {candidate.aliases.length > 0 && <p><strong>Алиасы:</strong> {candidate.aliases.join(', ')}</p>}
      </section>
      {(candidate.scope_proposals.length > 0 || candidate.related_terms.length > 0 || candidate.scope_keys.length > 0) && <section className={styles.section}>
        <h3>Связи и применимость</h3>
        {candidate.scope_proposals.map((item) => <p key={item.id}><Badge tone={item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'warn'}>{item.status}</Badge> {item.scope_type}: {item.name} · {item.role}{item.term_name ? ` · термин ${item.term_name}` : ''}{item.rejection_reason ? ` · ${item.rejection_reason}` : ''}</p>)}
        {candidate.related_terms.map((item) => <p key={`${item.term}:${item.scope}`}><strong>{item.term}</strong> → {item.scope} ({item.status})</p>)}
        {candidate.scope_keys.length > 0 && <p><strong>Известные скоупы:</strong> {candidate.scope_keys.join(', ')}</p>}
      </section>}
      <section className={styles.section}><h3>Основание</h3>
        <p>Фрагментов: {candidate.evidence_section_ids.length}; уверенность: {Math.round(candidate.extraction_confidence * 100)}%</p>
        {evidence.data?.sections.map((section) => <blockquote key={section.id} className={styles.excerpt}><span>{section.label}</span><p>{section.text}</p></blockquote>)}
        {evidence.data && evidence.data.sections.length > 0 && <strong>{evidence.data.document_title}</strong>}
        {candidate.scope_rationale && <p>{candidate.scope_rationale}</p>}
        {candidate.unmatched_scope_names.length > 0 && <p><strong>Не сопоставлено:</strong> {candidate.unmatched_scope_names.join(', ')}</p>}
      </section>
      {rejecting && <label className={styles.field}><span>Причина отклонения *</span><textarea rows={3} maxLength={2000} value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} /></label>}
      {error && <div className={styles.warning} role="alert">{error}</div>}
    </div>
  </Modal>;
}
