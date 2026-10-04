import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button, DataTable, EntityPageV2, Modal, Tab, Textarea, type DataTableColumn } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { adminApi, type MemoryCandidateTags, type SemanticMemoryAdminDetail, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { useErrorToast } from '@/shared/ui/Toast';
import { memoryLinksFields, otherMemoryLinksFields } from './MemoryLinksFields';
import MemoryEvidence from './MemoryEvidence';
import MemoryApplicabilityValue, { applicabilityLabel } from './MemoryApplicabilityValue';
import MemoryContentView, { MemoryContentViewToggle, memoryContentPreview } from './MemoryContentView';
import contentStyles from './MemoryContentView.module.css';
import { candidateBlockers, candidateTypeLabels } from './MemoryReviewTable';
import styles from './MemoryReviewDialog.module.css';

type Props = { candidate?: ShadowMemoryCandidate; published?: SemanticMemoryAdminDetail; initialTab?: string };
const stateLabels: Record<string, string> = { active: 'Активна', uncertain: 'Есть противоречия', stale: 'Устарела',
  extracted: 'Извлечена', needs_review: 'На проверке', conflict: 'Есть конфликт', resolved: 'Утверждена', rejected: 'Отклонена', superseded: 'Заменена' };
export default function MemoryDetail({ candidate, published, initialTab = 'overview' }: Props) {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const queryClient = useQueryClient();
  const backPath = `/admin/memory?tab=${candidate ? 'review' : 'memory'}`;
  const [activeTab, setActiveTab] = useState(initialTab);
  const [jsonMode, setJsonMode] = useState(false);
  const [tagDraft, setTagDraft] = useState<MemoryCandidateTags | null>(null);
  const [editingLinks, setEditingLinks] = useState(false);
  const [applicabilityChanged, setApplicabilityChanged] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const scopes = useQuery({ queryKey: qk.admin.memory.scopes(), queryFn: () => adminApi.getMemoryScopes() });
  const terms = useQuery({ queryKey: qk.admin.memory.termCatalog(), queryFn: () => adminApi.getMemoryTermCatalog() });
  const canReview = Boolean(candidate && ['extracted', 'needs_review', 'conflict'].includes(candidate.resolution_status));
  const baseTags: MemoryCandidateTags = {
    scope_ids: candidate?.scope_ids ?? scopes.data?.filter((scope) => published?.scope_keys.includes(scope.key)).map((scope) => scope.id) ?? [],
    glossary_term_ids: [...new Set(candidate?.glossary_term_ids ?? (published?.related_entities ?? []).filter((entity) => entity.type === 'glossary_term').map((entity) => String(entity.id)))],
    reason: '',
  };
  const draft = tagDraft ?? baseTags;
  const isEditingLinks = canReview || editingLinks;
  const itemId = published?.id ?? candidate?.published_item_id;
  const blocked = Boolean(candidate && (!candidate.content_valid || candidate.conflict_ids.length
    || !applicabilityChanged && candidate.approval_blockers.length > 0));
  const decision = useMutation({
    mutationFn: async (action: 'approve' | 'reject') => {
      if (!candidate) throw new Error('Кандидат не найден');
      if (action === 'reject') return adminApi.rejectShadowMemoryCandidate(candidate.id, rejectReason.trim());
      return adminApi.approveShadowMemoryCandidate(candidate.id, { tags: draft });
    },
    onError: (error: Error) => showError(error.message),
    onSuccess: async (result, action) => {
      if (action === 'approve') {
        queryClient.setQueryData(qk.admin.memory.candidate(result.id), result);
        setTagDraft(null); setApplicabilityChanged(false);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.admin.memory.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.glossary.all() }),
        queryClient.invalidateQueries({ queryKey: qk.collections.glossaryAll() }),
      ]);
      if (action === 'reject') navigate(backPath);
    },
  });
  const saveLinks = useMutation({
    mutationFn: () => {
      if (!itemId) throw new Error('Утверждённый атом не найден');
      return adminApi.updateSemanticMemoryLinks(itemId, draft);
    },
    onError: (error: Error) => showError(error.message),
    onSuccess: async (result) => {
      queryClient.setQueryData(qk.admin.memory.item(result.id), result);
      await queryClient.invalidateQueries({ queryKey: qk.admin.memory.all() });
      setTagDraft(null); setEditingLinks(false); setApplicabilityChanged(false);
    },
  });
  const handleLinksChange = (value: MemoryCandidateTags) => {
    if (value.scope_ids.join(',') !== draft.scope_ids.join(',')) setApplicabilityChanged(true);
    setTagDraft(value);
  };
  const linksPending = decision.isPending || saveLinks.isPending || scopes.isLoading || terms.isLoading;
  const content = candidate?.content ?? published?.content ?? {};
  const subject = candidate?.subject ?? published?.subject ?? 'Память';
  const type = candidate?.candidate_type ?? published?.item_type ?? '';
  const state = candidate?.resolution_status ?? published?.state ?? '';
  const scopeKeys = scopes.data?.filter((scope) => draft.scope_ids.includes(scope.id)).map((scope) => scope.key)
    ?? candidate?.scope_keys ?? published?.scope_keys ?? [];
  const entities = candidate?.related_entities ?? published?.related_entities ?? [];
  const termIds = draft.glossary_term_ids;
  const scopeNames = (type: string) => scopeKeys.filter((key) => key.startsWith(`${type}.`)).map((key) => scopes.data?.find((scope) => scope.key === key)?.name ?? key);
  const termNames = termIds.map((id) => terms.data?.find((term) => term.id === id)?.canonical_term
    ?? String(entities.find((entity) => entity.id === id)?.name ?? id));
  const applicabilityFields: FieldConfig[] = [
    { key: 'projects', label: 'Проекты — где действует', type: 'tags', editable: false },
    { key: 'teams', label: 'Команды — кому действует', type: 'tags', editable: false },
  ];
  const applicability = {
    projects: scopeNames('project').length ? scopeNames('project') : ['Вне проектов'],
    teams: scopeNames('team').length ? scopeNames('team') : ['Без адресата'],
  };
  const additionalApplicability: Record<string, unknown> = { ...published?.applicability,
    ...('conditions' in content ? { conditions: content.conditions } : {}),
    ...('applicability_conditions' in content ? { applicability_conditions: content.applicability_conditions } : {}) };
  const extraApplicabilityFields: FieldConfig[] = Object.entries(additionalApplicability)
    .filter(([, value]) => value !== undefined && value !== null && value !== '' && !(Array.isArray(value) && !value.length))
    .map(([key]) => ({ key, label: applicabilityLabel(key), type: 'custom', editable: false,
      render: (value: unknown) => <MemoryApplicabilityValue value={value} /> }));
  const information = { subject, type: candidateTypeLabels[type] ?? type, ...applicability, ...additionalApplicability, terms: termNames,
    relationships: [...entities.filter((entity) => entity.type !== 'glossary_term').map((entity) => String(entity.name ?? entity.type ?? entity.id)),
      ...(published?.relations.map((relation) => `${relation.relation_type}: ${relation.target_id}`) ?? [])],
    state: stateLabels[state] ?? state, confidence: `${Math.round((candidate?.extraction_confidence ?? published?.confidence ?? 0) * 100)}%`,
    source_count: published?.source_count ?? (candidate ? 1 : 0), claim_count: published?.claim_count ?? 1,
    last_verified_at: published?.last_verified_at, updated_at: published?.updated_at };
  const sourceColumns: DataTableColumn<SemanticMemoryAdminDetail['sources'][number]>[] = [
    { key: 'document_id', label: 'ДОКУМЕНТ', render: (row) => <span title={row.document_id}>{row.document_title || row.document_id}</span> },
    { key: 'label', label: 'ФРАГМЕНТ', render: (row) => row.label || row.section_id },
    { key: 'start_offset', label: 'НАЧАЛО', width: 100, render: (row) => row.start_offset ?? '—' },
    { key: 'end_offset', label: 'КОНЕЦ', width: 100, render: (row) => row.end_offset ?? '—' },
  ];
  const claimColumns: DataTableColumn<SemanticMemoryAdminDetail['claims'][number]>[] = [
    { key: 'document_id', label: 'ДОКУМЕНТ', render: (row) => published?.sources.find((source) => source.document_id === row.document_id)?.document_title || row.document_id },
    { key: 'state', label: 'СОСТОЯНИЕ', render: (row) => stateLabels[row.state] ?? row.state },
    { key: 'confidence', label: 'УВЕРЕННОСТЬ', render: (row) => `${Math.round(row.confidence * 100)}%` },
    { key: 'updated_at', label: 'ОБНОВЛЕНО', render: (row) => new Date(row.updated_at).toLocaleString('ru-RU') },
  ];
  const representedProjects = scopes.data?.filter((scope) => draft.scope_ids.includes(scope.id) && scope.project_id)
    .map((scope) => scope.project_id!) ?? [];
  const otherLinks = otherMemoryLinksFields(entities.filter((entity) => entity.type !== 'glossary_term'), published?.relations ?? [],
    new Set([...draft.scope_ids, ...scopeKeys, ...representedProjects, ...termIds]));
  const linksFields = memoryLinksFields({ scopes: scopes.data ?? [], terms: terms.data ?? [], value: draft,
    onChange: handleLinksChange, pending: linksPending });
  return <><EntityPageV2 title={subject} mode="view" breadcrumbs={[
    { label: 'Мемори', href: '/admin/memory' }, { label: candidate ? 'На проверке' : 'Утверждённая память', href: backPath }, { label: subject },
  ]} backPath={backPath} defaultTab={initialTab} onTabChange={setActiveTab} actionButtons={<>
    {canReview && <>
      <Button variant="danger" disabled={decision.isPending} onClick={() => { setRejecting(true); decision.reset(); }}>Отклонить</Button>
      <Button disabled={decision.isPending || blocked || scopes.isLoading || terms.isLoading || scopes.isError || terms.isError}
        onClick={() => { decision.reset(); decision.mutate('approve'); }}>{decision.isPending ? 'Сохраняю…' : 'Утвердить'}</Button>
    </>}
    {!canReview && itemId && (editingLinks ? <>
      <Button variant="outline" disabled={saveLinks.isPending} onClick={() => { setTagDraft(null); setEditingLinks(false); setApplicabilityChanged(false); }}>Отмена</Button>
      <Button disabled={linksPending || scopes.isError || terms.isError} onClick={() => saveLinks.mutate()}>{saveLinks.isPending ? 'Сохраняю…' : 'Сохранить'}</Button>
    </> : <Button variant="outline" disabled={linksPending || scopes.isError || terms.isError}
      onClick={() => setEditingLinks(true)}>Редактировать</Button>)}
  </>}>
    <Tab title="Обзор" id="overview" layout="grid">
      <Block title="Основная информация" icon="database" iconVariant="info" width="1/2" fields={[
        { key: 'subject', label: 'Тема', type: 'text', editable: false },
        { key: 'type', label: 'Тип знания', type: 'badge', editable: false },
        ...applicabilityFields,
        ...extraApplicabilityFields,
        { key: 'terms', label: 'Термины', type: 'tags', editable: false },
        { key: 'relationships', label: 'Связи', type: 'tags', editable: false },
      ]} data={information} />
      <Block title="Состояние и уверенность" icon="activity" iconVariant="success" width="1/2" fields={[
        { key: 'state', label: 'Статус', type: 'badge', badgeTone: canReview ? 'warn' : state === 'active' || state === 'resolved' ? 'success' : 'neutral', editable: false },
        { key: 'confidence', label: candidate ? 'Оценка извлекателя' : 'Уверенность', type: 'text', editable: false },
        { key: 'source_count', label: 'Источники', type: 'number', editable: false },
        { key: 'claim_count', label: 'Утверждения', type: 'number', editable: false },
        ...(!candidate ? [
          { key: 'last_verified_at', label: 'Последняя проверка', type: 'date' as const, editable: false },
          { key: 'updated_at', label: 'Обновлено', type: 'date' as const, editable: false },
        ] : []),
      ]} data={information} />
      <Block title="Содержание памяти" icon="file-text" width="full" headerLabels="Первые 24 строки">
        <p className={contentStyles.preview}>{memoryContentPreview(type, content) || 'Содержание не извлечено'}</p>
      </Block>
    </Tab>
    <Tab title="Содержимое" id="content" layout="grid">
      <Block title="Содержание памяти" icon="file-text" iconVariant="primary" width="full"
        headerLabels={jsonMode ? 'Каноническое содержание' : 'По разделам'}
        headerActions={<MemoryContentViewToggle jsonMode={jsonMode} onChange={setJsonMode} />}>
        <MemoryContentView type={type} content={content} error={candidate?.content_error} jsonMode={jsonMode} />
      </Block>
    </Tab>
    <Tab title="Связи и применимость" id="relations" layout="grid">
      <Block title="Применимость" icon="filter" iconVariant="info" width="full" fields={extraApplicabilityFields.length ? extraApplicabilityFields : undefined} data={additionalApplicability}>
        <p>Дополнительные условия применимости не указаны.</p>
      </Block>
      <Block title="Связи" icon="git-branch" iconVariant="primary" width="full" editable={isEditingLinks}
        fields={[...linksFields, ...otherLinks.fields]} data={{ ...draft, ...otherLinks.data }}
        headerLabels={isEditingLinks ? 'Редактирование' : undefined} />
      {(scopes.isError || terms.isError) && <p role="alert">Не удалось загрузить каталоги. <Button variant="outline" onClick={() => { scopes.refetch(); terms.refetch(); }}>Повторить</Button></p>}
      {candidate && candidateBlockers(candidate).length > 0 && !applicabilityChanged && <ul>{candidateBlockers(candidate).map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </Tab>
    <Tab title="Происхождение" id="provenance" layout="full">
      {published && <>
        <Block title="Документы и фрагменты" icon="file" iconVariant="info"><DataTable columns={sourceColumns}
          data={published.sources.map((source, index) => ({ ...source, id: `${source.document_id}:${source.section_id}:${index}` }))}
          keyField="id" emptyText="Источники не найдены" /></Block>
        <Block title="Утверждения из источников" icon="database" iconVariant="info"><DataTable columns={claimColumns} data={published.claims} keyField="id" emptyText="Утверждений нет" /></Block>
      </>}
      <Block title={candidate?.document_title || 'Фрагменты документов'} icon="file-text" iconVariant="info">
        <MemoryEvidence candidateIds={candidate ? [candidate.id] : (published?.claims.map((claim) => claim.approved_candidate_id).filter((id): id is string => Boolean(id)) ?? [])}
          enabled={activeTab === 'provenance'} />
      </Block>
    </Tab>
  </EntityPageV2>
    <Modal open={rejecting} title="Отклонение кандидата" onClose={() => { if (!decision.isPending) setRejecting(false); }}
      footer={<><Button variant="outline" disabled={decision.isPending} onClick={() => setRejecting(false)}>Отмена</Button>
        <Button variant="danger" disabled={decision.isPending || !rejectReason.trim()} onClick={() => decision.mutate('reject')}>
          {decision.isPending ? 'Сохраняю…' : 'Отклонить'}</Button></>}>
      <div className={styles.panel}>
        <label className={styles.field}>Причина отклонения *<Textarea rows={3} maxLength={2000} value={rejectReason} disabled={decision.isPending} onChange={(event) => setRejectReason(event.target.value)} /></label>
        <p>Причина будет учтена при повторном извлечении.</p>
        {decision.isError && <p className={styles.warning} role="alert">{decision.error.message}</p>}
      </div>
    </Modal>
  </>;
}
