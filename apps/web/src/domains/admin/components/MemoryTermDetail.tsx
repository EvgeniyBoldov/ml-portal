import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Badge, Button, Checkbox, EntityPageV2, Modal, Tab, Textarea } from '@/shared/ui';
import { Block } from '@/shared/ui/GridLayout';
import { adminApi, type AdminGlossaryTerm, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { useErrorToast } from '@/shared/ui/Toast';
import MemoryEvidence from './MemoryEvidence';
import styles from './MemoryTermDetail.module.css';

type Props = { candidate?: ShadowMemoryCandidate; term?: AdminGlossaryTerm };
const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').toLocaleLowerCase();

/** Terminology is reviewed independently from scoped knowledge. */
export default function MemoryTermDetail({ candidate, term }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const [activeTab, setActiveTab] = useState('term');
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [replaceDefinition, setReplaceDefinition] = useState(false);
  const [replaceReason, setReplaceReason] = useState('');
  const glossary = useQuery({ queryKey: qk.admin.glossary.all(), queryFn: () => adminApi.getGlossary(), enabled: Boolean(candidate) });
  const existing = glossary.data?.find((entry) => entry.normalized_term === candidate?.normalized_subject);
  const definition = candidate ? String(candidate.content.definition ?? '') : term?.definition ?? '';
  const changedDefinition = Boolean(existing && normalize(existing.definition) !== normalize(definition));
  const canReview = Boolean(candidate && ['extracted', 'needs_review', 'conflict'].includes(candidate.resolution_status));
  const backPath = `/admin/memory?tab=${candidate ? 'review' : 'glossary'}`;
  const decision = useMutation({
    mutationFn: (action: 'approve' | 'reject') => {
      if (!candidate) throw new Error('Термин не найден');
      return action === 'reject' ? adminApi.rejectShadowMemoryCandidate(candidate.id, rejectReason.trim())
        : adminApi.approveShadowMemoryCandidate(candidate.id, changedDefinition
          ? { replace_existing_definition: true, reason: replaceReason.trim() } : {});
    },
    onError: (error: Error) => showError(error.message),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.admin.memory.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.glossary.all() }),
        queryClient.invalidateQueries({ queryKey: qk.collections.glossaryAll() }),
      ]);
      navigate(backPath);
    },
  });
  const subject = candidate?.subject ?? term?.canonical_term ?? 'Термин';
  const aliases = candidate?.aliases ?? term?.aliases ?? [];
  return <>
    <EntityPageV2 title={subject} mode="view" backPath={backPath} onTabChange={setActiveTab}
      breadcrumbs={[{ label: 'Мемори', href: '/admin/memory' }, { label: candidate ? 'На проверке' : 'Глоссарий', href: backPath }, { label: subject }]}
      actionButtons={<>
        <Button variant="outline" onClick={() => navigate(backPath)}>К списку</Button>
        {canReview && <>
          <Button variant="danger" disabled={decision.isPending} onClick={() => setRejecting(true)}>Отклонить</Button>
          <Button disabled={decision.isPending || !candidate?.content_valid || Boolean(candidate?.conflict_ids.length)
            || glossary.isLoading || glossary.isError || changedDefinition && (!replaceDefinition || !replaceReason.trim())}
            onClick={() => decision.mutate('approve')}>Утвердить термин</Button>
        </>}
      </>}>
      <Tab title="Термин" id="term" layout="grid">
        <Block title="Термин" icon="tag" width="full" headerLabels={<Badge tone={canReview ? 'warn' : term?.is_active ? 'success' : 'neutral'}>
          {candidate ? canReview ? 'На проверке' : candidate.resolution_status === 'resolved' ? 'Утверждён' : 'Отклонён' : term?.is_active ? 'Утверждён' : 'Выключен'}
        </Badge>} fields={[
          { key: 'subject', label: 'Название', type: 'text', editable: false },
          { key: 'aliases', label: 'Алиасы', type: 'tags', editable: false },
          { key: 'definition', label: 'Расшифровка / определение', type: 'textarea', editable: false },
        ]} data={{ subject, aliases, definition }} />
        {changedDefinition && <Block title="Изменение определения" icon="edit" width="full">
          <div className={styles.panel}>
            <p>Действующее определение: {existing?.definition}</p>
            {existing && <Link to={`/admin/memory/terms/${existing.id}`}>Открыть утверждённый термин</Link>}
            {canReview && <>
              <Checkbox checked={replaceDefinition} onChange={setReplaceDefinition} disabled={decision.isPending} label="Подтвердить новое определение" />
              {replaceDefinition && <label className={styles.field}>Причина изменения *<Textarea value={replaceReason} maxLength={2000}
                disabled={decision.isPending} onChange={(event) => setReplaceReason(event.target.value)} /></label>}
            </>}
          </div>
        </Block>}
        {glossary.isError && <p role="alert">Не удалось проверить каталог терминов. <Button variant="outline" onClick={() => glossary.refetch()}>Повторить</Button></p>}
        {candidate?.content_error && <p role="alert">{candidate.content_error}</p>}
      </Tab>
      <Tab title="Происхождение" id="provenance" layout="full">
        <Block title={candidate?.document_title || 'Источник термина'} icon="file-text">
          <MemoryEvidence candidateIds={candidate ? [candidate.id] : term?.approved_candidate_id ? [term.approved_candidate_id] : []} enabled={activeTab === 'provenance'} />
        </Block>
      </Tab>
    </EntityPageV2>
    <Modal open={rejecting} title="Отклонение термина" onClose={() => { if (!decision.isPending) setRejecting(false); }}
      footer={<><Button variant="outline" disabled={decision.isPending} onClick={() => setRejecting(false)}>Отмена</Button>
        <Button variant="danger" disabled={decision.isPending || !rejectReason.trim()} onClick={() => decision.mutate('reject')}>Отклонить</Button></>}>
      <label className={styles.field}>Причина отклонения *<Textarea value={rejectReason} maxLength={2000}
        disabled={decision.isPending} onChange={(event) => setRejectReason(event.target.value)} /></label>
    </Modal>
  </>;
}
