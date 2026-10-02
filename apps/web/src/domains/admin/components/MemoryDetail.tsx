import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Checkbox, DataTable, EntityPageV2, Modal, Tab, Textarea, type DataTableColumn } from '@/shared/ui';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { adminApi, type MemoryCandidateTags, type SemanticMemoryAdminDetail, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { useErrorToast } from '@/shared/ui/Toast';
import MemoryCandidateTagEditor from './MemoryCandidateTagEditor';
import MemoryEvidence from './MemoryEvidence';
import { contentFieldLabels } from './MemoryContentView';
import { candidateBlockers, candidateTypeLabels, readinessLabels } from './MemoryReviewTable';
import styles from './MemoryReviewDialog.module.css';

type Props = { candidate?: ShadowMemoryCandidate; published?: SemanticMemoryAdminDetail };
const stateLabels: Record<string, string> = { active: 'Активна', uncertain: 'Есть противоречия', stale: 'Устарела',
  extracted: 'Извлечена', needs_review: 'На проверке', conflict: 'Есть конфликт', resolved: 'Утверждена', rejected: 'Отклонена', superseded: 'Заменена' };
const contentFields = (content: Record<string, unknown>): FieldConfig[] => Object.entries(content)
  .filter(([key, value]) => key !== 'steps' && value !== null && value !== '' && !(Array.isArray(value) && !value.length))
  .map(([key, value]) => ({ key, label: contentFieldLabels[key] ?? key.split('_').join(' '), editable: false,
    type: Array.isArray(value) ? 'tags' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean'
      : typeof value === 'object' ? 'json' : 'textarea' }));

function ProcedureSteps({ steps }: { steps: unknown }) {
  if (!Array.isArray(steps) || !steps.length) return <p>Шаги не указаны.</p>;
  const rows = steps.map((step, index) => {
    const value = step && typeof step === 'object' ? step as Record<string, unknown> : {};
    return { id: String(index), order: Number(value.order ?? index + 1), instruction: String(value.instruction ?? ''),
      expected_result: String(value.expected_result ?? ''), confirmation_required: Boolean(value.confirmation_required) };
  });
  const columns: DataTableColumn<typeof rows[number]>[] = [
    { key: 'order', label: '№', width: 60 },
    { key: 'instruction', label: 'ИНСТРУКЦИЯ' },
    { key: 'expected_result', label: 'ОЖИДАЕМЫЙ РЕЗУЛЬТАТ' },
    { key: 'confirmation_required', label: 'ПОДТВЕРЖДЕНИЕ', width: 150,
      render: (row) => <Badge tone={row.confirmation_required ? 'warn' : 'neutral'}>{row.confirmation_required ? 'Требуется' : 'Нет'}</Badge> },
  ];
  return <DataTable columns={columns} data={rows} keyField="id" />;
}

export default function MemoryDetail({ candidate, published }: Props) {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const queryClient = useQueryClient();
  const backPath = `/admin/memory?tab=${candidate ? 'review' : 'memory'}`;
  const [activeTab, setActiveTab] = useState('overview');
  const [tagDraft, setTagDraft] = useState<MemoryCandidateTags>({ scope_ids: candidate?.scope_ids ?? [],
    company_wide: false, glossary_term_ids: candidate?.glossary_term_ids ?? [], reason: '' });
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [replaceDefinition, setReplaceDefinition] = useState(false);
  const [replaceReason, setReplaceReason] = useState('');
  const scopes = useQuery({ queryKey: qk.admin.memory.scopes(), queryFn: () => adminApi.getMemoryScopes() });
  const terms = useQuery({ queryKey: qk.admin.memory.termCatalog(), queryFn: () => adminApi.getMemoryTermCatalog() });
  const glossary = useQuery({ queryKey: ['admin', 'glossary'], queryFn: () => adminApi.getGlossary(), enabled: candidate?.candidate_type === 'term' });
  const canReview = Boolean(candidate && ['extracted', 'needs_review', 'conflict'].includes(candidate.resolution_status));
  const hasLinks = candidate?.candidate_type === 'term' || tagDraft.scope_ids.length > 0 || tagDraft.glossary_term_ids.length > 0;
  const blocked = Boolean(candidate && (!candidate.content_valid || candidate.conflict_ids.length));
  const existingTerm = candidate?.candidate_type === 'term'
    ? glossary.data?.find((term) => term.normalized_term === candidate.normalized_subject) : undefined;
  const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const changedDefinition = Boolean(existingTerm && normalize(existingTerm.definition) !== normalize(String(candidate?.content.definition ?? '')));
  const decision = useMutation({
    mutationFn: async (action: 'approve' | 'reject') => {
      if (!candidate) throw new Error('Кандидат не найден');
      if (action === 'reject') return adminApi.rejectShadowMemoryCandidate(candidate.id, rejectReason.trim());
      if (changedDefinition && (!replaceDefinition || !replaceReason.trim())) throw new Error('Подтвердите замену определения и укажите причину.');
      await adminApi.updateShadowCandidateTags(candidate.id, tagDraft);
      return adminApi.approveShadowMemoryCandidate(candidate.id, changedDefinition
        ? { replace_existing_definition: true, reason: replaceReason.trim() } : {});
    },
    onError: (error: Error) => showError(error.message),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] }),
        queryClient.invalidateQueries({ queryKey: ['admin', 'glossary'] }),
        queryClient.invalidateQueries({ queryKey: ['collections', 'glossary', 'overview'] }),
      ]);
      navigate(backPath);
    },
  });
  const content = candidate?.content ?? published?.content ?? {};
  const fields = useMemo(() => contentFields(content), [content]);
  const subject = candidate?.subject ?? published?.subject ?? 'Память';
  const type = candidate?.candidate_type ?? published?.item_type ?? '';
  const state = candidate?.resolution_status ?? published?.state ?? '';
  const scopeKeys = candidate ? scopes.data?.filter((scope) => tagDraft.scope_ids.includes(scope.id)).map((scope) => scope.key) ?? []
    : published?.scope_keys ?? [];
  const entities = candidate?.related_entities ?? published?.related_entities ?? [];
  const termIds = candidate ? tagDraft.glossary_term_ids : entities.filter((entity) => entity.type === 'glossary_term').map((entity) => String(entity.id));
  const scopeNames = (type: string) => scopeKeys.filter((key) => key.startsWith(`${type}.`)).map((key) => scopes.data?.find((scope) => scope.key === key)?.name ?? key);
  const termNames = termIds.map((id) => terms.data?.find((term) => term.id === id)?.canonical_term
    ?? String(entities.find((entity) => entity.id === id)?.name ?? id));
  const information = { subject, type: candidateTypeLabels[type] ?? type,
    scope: candidate?.candidate_type === 'term' ? 'Общий глоссарий' : (scopeKeys.length || candidate && tagDraft.scope_ids.length) ? 'Выбранные области'
      : candidate && !hasLinks ? 'Не определена' : 'Вся компания',
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
  const relationColumns: DataTableColumn<SemanticMemoryAdminDetail['relations'][number]>[] = [
    { key: 'relation_type', label: 'СВЯЗЬ' }, { key: 'target_type', label: 'ТИП' }, { key: 'target_id', label: 'ЦЕЛЬ' },
  ];
  return <><EntityPageV2 title={subject} mode="view" breadcrumbs={[
    { label: 'Мемори', href: '/admin/memory' }, { label: candidate ? 'На проверке' : 'Утверждённая память', href: backPath }, { label: subject },
  ]} backPath={backPath} onTabChange={setActiveTab} actionButtons={<>
    <Button variant="outline" disabled={decision.isPending} onClick={() => navigate(backPath)}>К списку</Button>
    {canReview && <>
      <Button variant="danger" disabled={decision.isPending} onClick={() => { setRejecting(true); decision.reset(); }}>Отклонить</Button>
      <Button disabled={decision.isPending || blocked || !hasLinks || scopes.isLoading || terms.isLoading || scopes.isError || terms.isError
        || candidate?.candidate_type === 'term' && (glossary.isLoading || glossary.isError)}
        onClick={() => { decision.reset(); decision.mutate('approve'); }}>{decision.isPending ? 'Сохраняю…' : 'Утвердить'}</Button>
    </>}
  </>}>
    <Tab title="Обзор" id="overview" layout="grid">
      <Block title="Основная информация" icon="database" iconVariant="info" width="1/2" fields={[
        { key: 'subject', label: 'Тема', type: 'text', editable: false },
        { key: 'type', label: 'Тип знания', type: 'badge', editable: false },
        { key: 'scope', label: 'Применимость', type: 'badge', badgeTone: 'info', editable: false },
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
      {candidate && <Block title="Проверка перед утверждением" icon="shield" iconVariant="warning" width="full">
        <div className={styles.panel}>
          <Badge tone={blocked || !hasLinks ? 'warn' : 'success'}>{blocked ? readinessLabels[candidate.content_valid ? 'conflict' : 'content']
            : !hasLinks ? readinessLabels.scope : canReview ? readinessLabels.ready : stateLabels[state] ?? state}</Badge>
          {blocked && <ul>{candidateBlockers(candidate).map((reason) => <li key={reason}>{reason}</li>)}</ul>}
          {!hasLinks && <p>Для утверждения выберите хотя бы один проект, команду, продукт или термин на вкладке «Связи и применимость».</p>}
          {canReview && <p>Сверьте содержание с фрагментами на вкладке «Происхождение». Оценка извлекателя — самооценка модели.</p>}
        </div>
      </Block>}
    </Tab>
    <Tab title="Содержимое" id="content" layout="grid">
      <Block title="Содержание памяти" icon="file-text" iconVariant="primary" width="full" fields={fields} data={content} />
      {type === 'procedure' && <Block title="Шаги процедуры" icon="list" iconVariant="info" width="full"><ProcedureSteps steps={content.steps} /></Block>}
      {candidate?.aliases.length ? <Block title="Алиасы" width="full" fields={[{ key: 'aliases', label: 'Алиасы', type: 'tags', editable: false }]} data={candidate} /> : null}
      {existingTerm && <Block title="Действующее определение термина" icon="file-text" width="full">
        <div className={styles.panel}><p>{existingTerm.definition}</p>
          {changedDefinition && canReview && <>
            <Checkbox checked={replaceDefinition} onChange={setReplaceDefinition} disabled={decision.isPending} label="Утвердить замену определения" />
            {replaceDefinition && <label className={styles.field}>Причина замены *<Textarea value={replaceReason} maxLength={2000} disabled={decision.isPending} onChange={(event) => setReplaceReason(event.target.value)} /></label>}
          </>}
        </div>
      </Block>}
      {glossary.isError && candidate?.candidate_type === 'term' && <p role="alert">Не удалось проверить действующее определение. <Button variant="outline" onClick={() => glossary.refetch()}>Повторить</Button></p>}
    </Tab>
    <Tab title="Связи и применимость" id="relations" layout="grid">
      <Block title="Области и термины" icon="git-branch" iconVariant="primary" width="full" fields={canReview ? undefined : [
        { key: 'projects', label: 'Проекты', type: 'tags', editable: false },
        { key: 'teams', label: 'Команды', type: 'tags', editable: false },
        { key: 'products', label: 'Продукты', type: 'tags', editable: false },
        { key: 'terms', label: 'Термины', type: 'tags', editable: false },
      ]} data={{ projects: scopeNames('project'), teams: scopeNames('team'), products: scopeNames('product'), terms: termNames }}>
        {candidate && canReview && <MemoryCandidateTagEditor candidate={candidate} scopes={scopes.data ?? []} terms={terms.data ?? []}
          value={tagDraft} onChange={setTagDraft} pending={decision.isPending || scopes.isLoading || terms.isLoading}
          onRefreshCatalogs={() => { scopes.refetch(); terms.refetch(); }} />}
      </Block>
      {(scopes.isError || terms.isError) && <p role="alert">Не удалось загрузить каталоги. <Button variant="outline" onClick={() => { scopes.refetch(); terms.refetch(); }}>Повторить</Button></p>}
      {published && <Block title="Другие связи" icon="git-branch" width="full"><DataTable columns={relationColumns}
        data={published.relations.map((row, index) => ({ ...row, id: String(index) }))} keyField="id" emptyText="Других связей нет" /></Block>}
      {published && <Block title="Ограничения доступа и применимости" icon="shield" iconVariant="warning" width="full" fields={[
        { key: 'applicability', label: 'Дополнительная применимость', type: 'json', editable: false },
        { key: 'visibility', label: 'Видимость источника', type: 'json', editable: false },
      ]} data={published} />}
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
