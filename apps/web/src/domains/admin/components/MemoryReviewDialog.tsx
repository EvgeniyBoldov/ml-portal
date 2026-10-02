import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Checkbox, Modal, Tabs, Textarea } from '@/shared/ui';
import { adminApi, type MemoryCandidateTags, type MemoryScopeAdminItem, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import MemoryContentView from './MemoryContentView';
import MemoryCandidateTagEditor from './MemoryCandidateTagEditor';
import { candidateBlockers, candidateReadiness, candidateTypeLabels, readinessLabels } from './MemoryReviewTable';
import styles from './MemoryReviewDialog.module.css';

export type MemoryApproval = { reason?: string; replace_existing_definition?: boolean };

type Props = {
  candidate: ShadowMemoryCandidate;
  scopes: MemoryScopeAdminItem[];
  pending: boolean;
  onClose: () => void;
  onApprove: (decision: MemoryApproval) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
  onSaveTags: (draft: MemoryCandidateTags) => Promise<ShadowMemoryCandidate>;
};

const tabs = [
  { id: 'memory', label: 'Память' },
  { id: 'relations', label: 'Связи и применимость' },
  { id: 'document', label: 'Источник документа' },
];

export default function MemoryReviewDialog({ candidate, scopes, pending, onClose, onApprove, onReject, onSaveTags }: Props) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('memory');
  const evidence = useQuery({ queryKey: qk.admin.memory.candidateEvidence(candidate.id),
    queryFn: () => adminApi.getShadowCandidateEvidence(candidate.id), enabled: activeTab === 'document', retry: false });
  const glossary = useQuery({ queryKey: ['admin', 'glossary'], queryFn: () => adminApi.getGlossary(), enabled: candidate.candidate_type === 'term' });
  const termCatalog = useQuery({ queryKey: qk.admin.memory.termCatalog(), queryFn: () => adminApi.getMemoryTermCatalog() });
  const [tagDraft, setTagDraft] = useState<MemoryCandidateTags>({ scope_ids: candidate.scope_ids,
    company_wide: false, glossary_term_ids: candidate.glossary_term_ids ?? [], reason: '' });
  const hasLinks = tagDraft.scope_ids.length > 0 || tagDraft.glossary_term_ids.length > 0;
  const published = candidate.candidate_type === 'term'
    ? glossary.data?.find((term) => term.normalized_term === candidate.normalized_subject) : undefined;
  const definition = String(candidate.content?.definition ?? '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const changedDefinition = Boolean(published && published.definition.trim().replace(/\s+/g, ' ').toLocaleLowerCase() !== definition);
  const [replaceDefinition, setReplaceDefinition] = useState(false);
  const [replaceReason, setReplaceReason] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState('');
  const blocked = candidate.conflict_ids.length > 0 || !candidate.content_valid;
  const readiness = !hasLinks && !blocked ? 'scope' : candidateReadiness({ ...candidate, scope_ids: tagDraft.scope_ids,
    glossary_term_ids: tagDraft.glossary_term_ids, approval_blockers: [] });

  const approve = async () => {
    setError('');
    if (changedDefinition && (!replaceDefinition || !replaceReason.trim())) {
      setActiveTab('memory');
      setError('Подтвердите замену определения и укажите причину.');
      return;
    }
    try {
      await onSaveTags(tagDraft);
      await onApprove(changedDefinition ? { replace_existing_definition: true, reason: replaceReason.trim() } : {});
    }
    catch (reason) { setActiveTab('memory'); setError(reason instanceof Error ? reason.message : 'Не удалось утвердить кандидата'); }
  };
  const reject = async () => {
    if (!rejectReason.trim()) { setError('Укажите причину отклонения.'); return; }
    try { await onReject(rejectReason.trim()); }
    catch (reason) { setActiveTab('memory'); setError(reason instanceof Error ? reason.message : 'Не удалось отклонить кандидата'); }
  };

  return <Modal open title="Проверка памяти" onClose={() => { if (!pending) onClose(); }} size="lg" bodyClassName={styles.reviewBody}
    footer={<><Button variant="outline" disabled={pending} onClick={onClose}>Закрыть</Button>
      {rejecting ? <><Button variant="outline" disabled={pending} onClick={() => { setRejecting(false); setError(''); }}>Назад</Button>
        <Button variant="danger" disabled={pending || !rejectReason.trim()} onClick={reject}>{pending ? 'Сохраняю…' : 'Отклонить'}</Button></>
        : <><Button variant="danger" disabled={pending} onClick={() => { setRejecting(true); setActiveTab('memory'); setError(''); }}>Отклонить</Button>
          <Button disabled={pending || blocked || !hasLinks || candidate.candidate_type === 'term' && (glossary.isLoading || glossary.isError)} onClick={approve}>{pending ? 'Сохраняю…' : 'Утвердить'}</Button></>}</>}>
    <header className={styles.reviewIntro}><Badge tone="info">{candidateTypeLabels[candidate.candidate_type] ?? candidate.candidate_type}</Badge><h2>{candidate.subject}</h2></header>
    <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} className={styles.reviewTabs}>
      <div className={styles.tabScroll} key={activeTab}>
        {activeTab === 'memory' && <div className={styles.panel}>
          <section className={styles.statusCard}>
            <div className={styles.statusHeading}><h3>Статус утверждения</h3><Badge tone={blocked || !hasLinks ? 'warn' : 'success'}>{readinessLabels[readiness]}</Badge></div>
            {blocked ? <><ul>{candidateBlockers(candidate).map((item) => <li key={item}>{item}</li>)}</ul>
              {!candidate.content_valid && <p>Отклоните кандидата с причиной и повторите извлечение документа — агент получит замечание.</p>}
              {candidate.approval_blockers.length > 0 && <Button size="sm" variant="outline" onClick={() => setActiveTab('relations')}>Посмотреть применимость</Button>}
            </> : <p>Содержание прошло проверку формата. Подтвердите его по исходному документу перед утверждением.</p>}
          </section>
          {!hasLinks && <p>Для утверждения выберите хотя бы один проект, команду, продукт или термин на вкладке «Связи и применимость».</p>}
          <section className={styles.section}><h3>Содержание</h3><MemoryContentView content={candidate.content} />
            {candidate.aliases.length > 0 && <p><strong>Алиасы:</strong> {candidate.aliases.join(', ')}</p>}
          </section>
          {candidate.candidate_type === 'term' && glossary.isError && <p role="alert">Не удалось проверить действующее определение термина. Закройте и откройте кандидата для повторной загрузки.</p>}
          {candidate.candidate_type === 'term' && published && <section className={styles.section}><h3>Действующее определение</h3><p>{published.definition}</p>
            {changedDefinition && <><Checkbox checked={replaceDefinition} onChange={setReplaceDefinition} label="Утвердить замену определения" disabled={pending} />
              {replaceDefinition && <label className={styles.field} htmlFor="memory-replace-reason">Причина замены *<Textarea id="memory-replace-reason" rows={2} maxLength={2000} value={replaceReason} disabled={pending} onChange={(event) => setReplaceReason(event.target.value)} /></label>}</>}
          </section>}
          {rejecting && <section className={styles.section}><h3>Отклонение кандидата</h3><label className={styles.field} htmlFor="memory-reject-reason">Причина отклонения *<Textarea id="memory-reject-reason" rows={3} maxLength={2000} value={rejectReason} disabled={pending} onChange={(event) => setRejectReason(event.target.value)} /></label><p>Причина будет учтена при повторном извлечении.</p></section>}
          {error && <div className={styles.warning} role="alert">{error}</div>}
        </div>}
        {activeTab === 'relations' && <div className={styles.panel}>
          <MemoryCandidateTagEditor candidate={candidate} scopes={scopes} terms={termCatalog.data ?? []} value={tagDraft} onChange={setTagDraft}
            pending={pending} onRefreshCatalogs={() => {
              termCatalog.refetch(); queryClient.invalidateQueries({ queryKey: qk.admin.memory.scopes() });
            }} />
          {termCatalog.isError && <p role="alert">Не удалось загрузить каталог терминов. Нажмите «Обновить каталоги».</p>}
        </div>}
        {activeTab === 'document' && <div className={styles.panel}>
          <section className={styles.section}><h3>Документ-источник</h3><strong>{evidence.data?.document_title || candidate.document_title || 'Документ'}</strong>
            <p>Фрагментов-оснований: {candidate.evidence_section_ids.length}</p>
            <p>Уверенность извлекателя: {Math.round(candidate.extraction_confidence * 100)}%. Это самооценка модели.</p>
          </section>
          <section className={styles.section}><h3>Фрагменты, на которых основан кандидат</h3>
            <p>Сверьте формулировку, условия и ограничения памяти с текстом источника.</p>
            {evidence.isLoading && <p>Загружаем фрагменты документа…</p>}
            {evidence.isError && <div className={styles.warning} role="alert"><p>{evidence.error instanceof Error ? evidence.error.message : 'Не удалось загрузить фрагменты документа.'}</p><Button size="sm" variant="outline" onClick={() => evidence.refetch()}>Повторить загрузку</Button></div>}
            {evidence.data && !evidence.data.sections.length && <p>Фрагменты по сохранённым ссылкам не найдены. Подтвердить содержание по источнику не удалось.</p>}
            {evidence.data?.sections.map((section) => <blockquote key={section.id} className={`${styles.excerpt} ${styles.fullExcerpt}`}><span>{section.label}</span><p>{section.text}</p></blockquote>)}
          </section>
        </div>}
      </div>
    </Tabs>
  </Modal>;
}
