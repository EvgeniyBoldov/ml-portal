import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Checkbox, ConfirmDialog, DataTable, EntityPageV2, Input, Modal, Select, Tab, LifecycleDeleteDialog, type DataTableColumn } from '@/shared/ui';
import { adminApi, type AdminGlossaryTerm, type MemoryCandidateTags, type MemoryScopeAdminItem, type MemoryScopeProposalAdminItem, type SemanticMemoryAdminItem, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import MemoryReviewDialog, { type MemoryApproval } from '@/domains/admin/components/MemoryReviewDialog';
import MemoryBulkRejectDialog from '@/domains/admin/components/MemoryBulkRejectDialog';
import MemoryScopeProposalDialog from '@/domains/admin/components/MemoryScopeProposalDialog';
import MemoryActionsMenu from '@/domains/admin/components/MemoryActionsMenu';
import { reviewColumns } from '@/domains/admin/components/MemoryReviewTable';
import { scopeColumns, scopeTypeLabels, type ScopeTableRow } from '@/domains/admin/components/MemoryScopeTable';
import styles from './MemoryPage.module.css';

const slugifyScopeName = (value: string) => {
  const transliteration: Record<string, string> = { а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch', ы: 'y', э: 'e', ю: 'yu', я: 'ya', ь: '', ъ: '' };
  return value.toLocaleLowerCase().replace(/[а-яё]/g, (char) => transliteration[char] ?? char)
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
};

const glossaryColumns: DataTableColumn<AdminGlossaryTerm>[] = [
  { key: 'canonical_term', label: 'ТЕРМИН', sortable: true, filter: { kind: 'text', placeholder: 'Термин' }, render: (row) => <strong>{row.canonical_term}</strong> },
  { key: 'definition', label: 'ОПРЕДЕЛЕНИЕ', render: (row) => row.definition },
  { key: 'aliases', label: 'АЛИАСЫ', filter: { kind: 'text', placeholder: 'Алиас', getValue: (row) => row.aliases.join(' ') }, render: (row) => row.aliases.length ? row.aliases.join(', ') : '—' },
  { key: 'is_active', label: 'СТАТУС', width: 120, render: (row) => <Badge tone={row.is_active ? 'success' : 'warn'}>{row.is_active ? 'активен' : 'выключен'}</Badge> },
  { key: 'created_at', label: 'СОЗДАН', width: 170, render: (row) => row.created_at ? new Date(row.created_at).toLocaleString('ru-RU') : '—' },
  { key: 'updated_at', label: 'ОБНОВЛЁН', width: 170, render: (row) => row.updated_at ? new Date(row.updated_at).toLocaleString('ru-RU') : '—' },
];

const memoryColumns: DataTableColumn<SemanticMemoryAdminItem>[] = [
  { key: 'subject', label: 'ЗНАНИЕ', sortable: true, filter: { kind: 'text', placeholder: 'Знание', getValue: (row) => `${row.subject} ${row.content_text}` }, render: (row) => <div><strong>{row.subject}</strong><div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{row.content_text}</div></div> },
  { key: 'item_type', label: 'ТИП', width: 150, filter: { kind: 'select', placeholder: 'Все типы', options: ['description', 'relationship', 'rule', 'constraint', 'procedure', 'decision'].map((value) => ({ value, label: value })), getValue: (row) => row.item_type }, render: (row) => <Badge tone="neutral">{row.item_type}</Badge> },
  { key: 'scope_keys', label: 'СКОУПЫ', width: 260, filter: { kind: 'text', placeholder: 'Ключ скоупа', getValue: (row) => row.scope_keys.join(' ') }, render: (row) => row.scope_keys.length ? row.scope_keys.join(', ') : 'Без скоупа' },
  { key: 'state', label: 'СОСТОЯНИЕ', width: 150, filter: { kind: 'select', placeholder: 'Все состояния', options: ['active', 'uncertain', 'stale'].map((value) => ({ value, label: value })), getValue: (row) => row.state }, render: (row) => <Badge tone={row.state === 'active' ? 'success' : row.state === 'uncertain' ? 'warn' : 'danger'}>{row.state}</Badge> },
  { key: 'confidence', label: 'УВЕРЕННОСТЬ', width: 130, align: 'right', filter: { kind: 'select', placeholder: 'Любая', options: [{ value: 'high', label: '≥ 80%' }, { value: 'medium', label: '50–79%' }, { value: 'low', label: '< 50%' }], getValue: (row) => row.confidence >= 0.8 ? 'high' : row.confidence >= 0.5 ? 'medium' : 'low' }, render: (row) => `${Math.round(row.confidence * 100)}%` },
  { key: 'source_count', label: 'ИСТОЧНИКИ', width: 110, align: 'right', sortable: true, filter: { kind: 'select', placeholder: 'Любое число', options: [{ value: 'one', label: '1' }, { value: 'multiple', label: '2+' }], getValue: (row) => row.source_count > 1 ? 'multiple' : 'one' }, render: (row) => row.source_count },
];

export default function MemoryPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialTab = ['glossary', 'memory', 'review', 'scopes'].includes(searchParams.get('tab') ?? '') ? searchParams.get('tab')! : 'glossary';
  const [activeTab, setActiveTab] = useState(initialTab);
  const [query, setQuery] = useState('');
  const [memoryScopeType, setMemoryScopeType] = useState('');
  const [memoryScopeId, setMemoryScopeId] = useState('');
  const [memoryPage, setMemoryPage] = useState(0);
  const [selectedGlossaryIds, setSelectedGlossaryIds] = useState<Set<string | number>>(new Set());
  const [confirmGlossaryAction, setConfirmGlossaryAction] = useState<'delete' | 'deactivate' | 'activate' | null>(null);
  const [selectedMemoryIds, setSelectedMemoryIds] = useState<Set<string | number>>(new Set());
  const [confirmMemoryDeactivate, setConfirmMemoryDeactivate] = useState(false);
  const [selectedReviewIds, setSelectedReviewIds] = useState<Set<string | number>>(new Set());
  const [bulkReviewRejectIds, setBulkReviewRejectIds] = useState<string[] | null>(null);
  const [scopeProposalEditor, setScopeProposalEditor] = useState<MemoryScopeProposalAdminItem | null>(null);
  const [scopeEditor, setScopeEditor] = useState<MemoryScopeAdminItem | 'new' | null>(null);
  const [scopeToDelete, setScopeToDelete] = useState<MemoryScopeAdminItem | null>(null);
  const [scopeLifecycleAction, setScopeLifecycleAction] = useState<'delete' | 'restore'>('delete');
  const [reviewEditor, setReviewEditor] = useState<ShadowMemoryCandidate | null>(null);
  const [scopeForm, setScopeForm] = useState({ scope_type: 'team' as MemoryScopeAdminItem['scope_type'], key: '', name: '', aliases: '', is_all: false });
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const { data: memoryScopes, isLoading: scopesLoading, isError: scopesError } = useQuery({
    queryKey: qk.admin.memory.scopes(), queryFn: () => adminApi.getMemoryScopes(), enabled: activeTab === 'scopes' || activeTab === 'review' || activeTab === 'memory',
  });
  const saveScope = useMutation({
    mutationFn: () => {
      const payload = { ...scopeForm, aliases: scopeForm.aliases.split(',').map((value) => value.trim()).filter(Boolean) };
      return scopeEditor === 'new' ? adminApi.createMemoryScope(payload) : adminApi.updateMemoryScope(scopeEditor!.id, payload);
    },
    onSuccess: () => { setScopeEditor(null); queryClient.invalidateQueries({ queryKey: ['admin', 'memory', 'scopes'] }); },
  });
  const { data: glossary, isLoading: glossaryLoading, isError: glossaryError } = useQuery({
    queryKey: ['admin', 'glossary'],
    queryFn: () => adminApi.getGlossary(),
    enabled: activeTab === 'glossary',
  });
  const { data: memory, isLoading: memoryLoading, isError: memoryError } = useQuery({
    queryKey: ['admin', 'memory', 'approved', query, memoryScopeType, memoryScopeId, memoryPage],
    queryFn: () => adminApi.getSemanticMemory({
      query: query || undefined,
      scope_type: memoryScopeType || undefined, scope_id: memoryScopeId || undefined,
      limit: 100, offset: memoryPage * 100,
    }),
    enabled: activeTab === 'memory',
  });
  const { data: review, isLoading: reviewLoading, isError: reviewError } = useQuery({
    queryKey: qk.admin.memory.review(),
    queryFn: async () => {
      const rows: ShadowMemoryCandidate[] = [];
      for (let offset = 0; ; offset += 200) {
        const batch = await adminApi.getShadowMemoryCandidates('pending', { limit: 200, offset });
        rows.push(...batch);
        if (batch.length < 200) return rows;
      }
    },
    enabled: activeTab === 'review',
  });
  const { data: scopeProposals, isLoading: scopeProposalsLoading, isError: scopeProposalsError } = useQuery({
    queryKey: qk.admin.memory.scopeProposals(),
    queryFn: async () => {
      const rows: MemoryScopeProposalAdminItem[] = [];
      for (let offset = 0; ; offset += 200) {
        const batch = await adminApi.getMemoryScopeProposals('pending', { limit: 200, offset });
        rows.push(...batch);
        if (batch.length < 200) return rows;
      }
    },
    enabled: activeTab === 'scopes',
  });
  const selectedReviewCandidates = (review ?? []).filter((row) => selectedReviewIds.has(row.id));
  const retryableSnapshots = useQuery({
    queryKey: ['admin', 'memory', 'retryable-snapshots'],
    queryFn: () => adminApi.getRetryableShadowSnapshots(),
    enabled: activeTab === 'review',
  });
  const decision = useMutation({
    mutationFn: ({ row, action, body, reason }: { row: ShadowMemoryCandidate; action: 'approve' | 'reject'; body?: MemoryApproval; reason?: string }) => action === 'approve'
      ? adminApi.approveShadowMemoryCandidate(row.id, body ?? {})
      : adminApi.rejectShadowMemoryCandidate(row.id, reason ?? ''),
    onSuccess: (_result, { row }) => {
      setSelectedReviewIds((current) => new Set([...current].filter((id) => id !== row.id)));
      queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'glossary'] });
      queryClient.invalidateQueries({ queryKey: ['collections', 'glossary', 'overview'] });
    },
  });
  const scopeDecision = useMutation({
    mutationFn: ({ row, action, reason }: { row: MemoryScopeProposalAdminItem; action: 'approve' | 'reject'; reason?: string }) => action === 'approve'
      ? adminApi.approveMemoryScopeProposal(row.id, reason)
      : adminApi.rejectMemoryScopeProposal(row.id, reason ?? ''),
    onSuccess: () => { setScopeProposalEditor(null); queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] }); },
    onError: (error: Error) => showError(error.message || 'Не удалось обработать предложение скоупа'),
  });
  const saveCandidateTags = useMutation({
    mutationFn: ({ id, tags }: { id: string; tags: MemoryCandidateTags }) => adminApi.updateShadowCandidateTags(id, tags),
    onSuccess: (row) => {
      setReviewEditor(row);
      queryClient.invalidateQueries({ queryKey: qk.admin.memory.review() });
      showSuccess('Применимость и связи сохранены');
    },
  });
  const reextract = useMutation({
    mutationFn: (snapshotId: string) => adminApi.reextractShadowMemorySnapshot(snapshotId),
    onSuccess: (result) => {
      showSuccess(`Повторное извлечение запущено (попытка ${result.attempt_number}).`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
    },
    onError: (error: Error) => showError(error.message || 'Не удалось повторить извлечение'),
  });
  const deactivateMemory = useMutation({
    mutationFn: () => adminApi.deactivateSemanticMemory([...selectedMemoryIds].map(String)),
    onSuccess: () => {
      const count = selectedMemoryIds.size;
      setSelectedMemoryIds(new Set());
      setConfirmMemoryDeactivate(false);
      showSuccess(`Деактивировано записей: ${count}`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
    },
    onError: (error: Error) => showError(error.message || 'Не удалось деактивировать записи памяти'),
  });
  const selectedGlossaryEntries = (glossary ?? []).filter((entry) => selectedGlossaryIds.has(entry.id));
  const hasActiveGlossarySelection = selectedGlossaryEntries.some((entry) => entry.is_active);
  const canActivateGlossarySelection = selectedGlossaryEntries.some((entry) => !entry.is_active) &&
    selectedGlossaryEntries.every((entry) => Boolean(entry.definition.trim() && entry.approved_candidate_id));
  const glossaryAction = useMutation<{ deleted?: number; deactivated?: number; activated?: number }>({
    mutationFn: () => confirmGlossaryAction === 'delete'
      ? adminApi.deleteGlossaryTerms([...selectedGlossaryIds].map(String))
      : confirmGlossaryAction === 'activate'
        ? adminApi.activateGlossaryTerms([...selectedGlossaryIds].map(String))
        : adminApi.deactivateGlossaryTerms([...selectedGlossaryIds].map(String)),
    onSuccess: (result) => {
      const count = result.deleted ?? result.deactivated ?? result.activated ?? 0;
      setSelectedGlossaryIds(new Set());
      setConfirmGlossaryAction(null);
      showSuccess(confirmGlossaryAction === 'delete' ? `Удалено терминов: ${count}` : confirmGlossaryAction === 'activate' ? `Активировано терминов: ${count}` : `Деактивировано терминов: ${count}`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'glossary'] });
      queryClient.invalidateQueries({ queryKey: ['collections', 'glossary', 'overview'] });
    },
    onError: (error: Error) => showError(error.message || 'Не удалось изменить выбранные термины'),
  });
  const filteredGlossary = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return glossary ?? [];
    return (glossary ?? []).filter((row) => [row.canonical_term, ...row.aliases].join(' ').toLocaleLowerCase().includes(needle));
  }, [glossary, query]);
  const activeMemoryScopes = (memoryScopes ?? []).filter((scope) => scope.lifecycle_status === 'active');
  const memoryScopeTypes = [...new Set(activeMemoryScopes.map((scope) => scope.scope_type))].sort();
  const openScopeEditor = (row: MemoryScopeAdminItem) => {
    setScopeForm({ scope_type: row.scope_type, key: row.key, name: row.name, aliases: row.aliases.join(', '), is_all: row.is_all });
    setScopeEditor(row);
  };
  const scopeRows: ScopeTableRow[] = [
    ...(memoryScopes ?? []).map((scope): ScopeTableRow => ({ kind: 'published', id: `scope:${scope.id}`, scope_type: scope.scope_type, key: scope.key, name: scope.name, aliases: scope.aliases, status: scope.lifecycle_status, scope })),
    ...(scopeProposals ?? []).map((proposal): ScopeTableRow => ({ kind: 'proposal', id: `proposal:${proposal.id}`, scope_type: proposal.scope_type, key: proposal.proposed_key, name: proposal.name, aliases: proposal.aliases, status: proposal.status, proposal })),
  ];
  const openScopeRow = (row: ScopeTableRow) => {
    if (row.kind === 'proposal') setScopeProposalEditor(row.proposal);
    else if (row.scope.lifecycle_status === 'active') openScopeEditor(row.scope);
  };

  return (
    <>
    <EntityPageV2
      title="Мемори"
      defaultTab={initialTab}
      mode="view"
      breadcrumbs={[{ label: 'Мемори' }]}
      onTabChange={(tab) => { setActiveTab(tab); setQuery(''); }}
      headerActions={(activeTab === 'glossary' || activeTab === 'memory') ? <Input aria-label="Поиск в текущей вкладке" placeholder={activeTab === 'glossary' ? 'Поиск терминов' : 'Поиск по памяти'} value={query} onChange={(event) => { setQuery(event.target.value); setMemoryPage(0); setSelectedMemoryIds(new Set()); setSelectedGlossaryIds(new Set()); }} /> : null}
    >
      <Tab title="Глоссарий" id="glossary" layout="full">
        {glossaryError ? <p role="alert">Не удалось загрузить глоссарий.</p> : <DataTable
          columns={glossaryColumns} data={filteredGlossary} keyField="id" loading={glossaryLoading}
          emptyText="Термины не найдены" paginated pageSize={20} selectable
          selectedKeys={selectedGlossaryIds} onSelectionChange={setSelectedGlossaryIds}
          bulkActions={<div className={styles.selectionActions}>
            <MemoryActionsMenu disabled={glossaryAction.isPending} items={[
              { label: 'Активировать', disabled: !canActivateGlossarySelection, onClick: () => setConfirmGlossaryAction('activate') },
              { label: 'Деактивировать', disabled: !hasActiveGlossarySelection, onClick: () => setConfirmGlossaryAction('deactivate') },
              { label: 'Удалить', variant: 'danger', onClick: () => setConfirmGlossaryAction('delete') },
            ]} />
          </div>} />}
      </Tab>
      <Tab title="Память" id="memory" layout="full">
        <div className={styles.filterBar}>
          <label className={styles.scopeField}>Тип скоупа
            <Select value={memoryScopeType} options={[{ value: '', label: 'Все типы' }, { value: 'global', label: 'Без скоупа' }, ...memoryScopeTypes.map((value) => ({ value, label: value }))]} onChange={(value) => { setMemoryScopeType(value); setMemoryScopeId(''); setMemoryPage(0); setSelectedMemoryIds(new Set()); }} />
          </label>
          <label className={styles.scopeField}>Скоуп
            <Select value={memoryScopeId} options={[{ value: '', label: 'Все скоупы' }, ...activeMemoryScopes.filter((scope) => !memoryScopeType || scope.scope_type === memoryScopeType).map((scope) => ({ value: scope.id, label: `${scope.name} (${scope.key})` }))]} disabled={memoryScopeType === 'global'} onChange={(value) => { setMemoryScopeId(value); setMemoryPage(0); setSelectedMemoryIds(new Set()); }} />
          </label>
        </div>
        {memoryError ? <p role="alert">Не удалось загрузить утверждённую память.</p> : <DataTable key={`${memoryPage}:${memoryScopeType}:${memoryScopeId}:${query}`} columns={memoryColumns} data={memory?.items ?? []} keyField="id" loading={memoryLoading} emptyText="Утверждённой памяти с выбранными фильтрами нет" paginated pageSize={20} onRowClick={(row) => navigate(`/admin/memory/${row.id}`)} selectable selectedKeys={selectedMemoryIds} onSelectionChange={setSelectedMemoryIds} bulkActions={<Button size="sm" variant="outline" disabled={deactivateMemory.isPending} onClick={() => setConfirmMemoryDeactivate(true)}>Деактивировать</Button>} />}
        {(memoryPage > 0 || (memory?.total ?? 0) > 100) && <div className={styles.pager}>
          <Button size="sm" variant="outline" disabled={memoryPage === 0} onClick={() => { setMemoryPage(memoryPage - 1); setSelectedMemoryIds(new Set()); }}>Назад</Button>
          <span>{Math.min(memoryPage * 100 + 1, memory?.total ?? 0)}–{Math.min((memoryPage + 1) * 100, memory?.total ?? 0)} из {memory?.total ?? 0}</span>
          <Button size="sm" variant="outline" disabled={(memoryPage + 1) * 100 >= (memory?.total ?? 0)} onClick={() => { setMemoryPage(memoryPage + 1); setSelectedMemoryIds(new Set()); }}>Далее</Button>
        </div>}
      </Tab>
      <Tab title="На проверке" id="review" layout="full">
        {review?.some((row) => row.document_access_scope && row.document_access_scope !== 'global') && <p className={styles.reviewHint}>Термины общего глоссария извлекаются только из документов с глобальным доступом. Документы с доступом к коллекции дают кандидаты памяти, но не термины общего глоссария.</p>}
        {reviewError ? <p role="alert">Не удалось загрузить очередь проверки.</p> : <DataTable
          columns={reviewColumns} data={review ?? []} keyField="id"
          className={styles.reviewTable} selectable selectedKeys={selectedReviewIds} onSelectionChange={setSelectedReviewIds}
          bulkActions={<MemoryActionsMenu items={[{
            label: 'Отклонить выбранные', variant: 'danger', disabled: !selectedReviewCandidates.length,
            onClick: () => setBulkReviewRejectIds(selectedReviewCandidates.map((row) => row.id)),
          }]} />}
          loading={reviewLoading} emptyText="Кандидатов на проверке нет" paginated pageSize={20}
          onRowClick={setReviewEditor} />}
      </Tab>
      <Tab title="Скоупы" id="scopes" layout="full" actions={[<Button key="create-scope" onClick={() => { setScopeForm({ scope_type: 'team', key: '', name: '', aliases: '', is_all: false }); setScopeEditor('new'); }}>Создать скоуп</Button>]}>
        {scopesError || scopeProposalsError ? <p role="alert">Не удалось загрузить скоупы памяти и предложения.</p> : <DataTable columns={scopeColumns({ onReview: setScopeProposalEditor, onEdit: openScopeEditor, onLifecycle: (scope, action) => { setScopeLifecycleAction(action); setScopeToDelete(scope); } })} data={scopeRows} keyField="id" loading={scopesLoading || scopeProposalsLoading} emptyText="Скоупов пока нет" paginated pageSize={20} onRowClick={openScopeRow} />}
      </Tab>
    </EntityPageV2>
    <Modal open={Boolean(scopeEditor)} title={scopeEditor === 'new' ? 'Новый скоуп памяти' : 'Изменить скоуп памяти'} onClose={() => setScopeEditor(null)}>
      <div style={{ display: 'grid', gap: 12 }}>
        <label className={styles.scopeField}>Тип<Select options={Object.entries(scopeTypeLabels).map(([value, label]) => ({ value, label }))} value={scopeForm.scope_type} disabled={scopeEditor !== 'new'} onChange={(value) => { const nextType = value as MemoryScopeAdminItem['scope_type']; setScopeForm({ ...scopeForm, scope_type: nextType, key: scopeForm.is_all ? `${nextType}.all` : `${nextType}.${slugifyScopeName(scopeForm.name)}` }); }} /></label>
        {scopeEditor !== 'new' && <small style={{ color: 'var(--muted)' }}>Тип и ключ фиксируют идентичность скоупа; здесь можно изменить название и алиасы.</small>}
        <label className={styles.scopeField}>Название<Input value={scopeForm.name} onChange={(event) => setScopeForm({ ...scopeForm, name: event.target.value, key: scopeForm.is_all ? scopeForm.key : `${scopeForm.scope_type}.${slugifyScopeName(event.target.value)}` })} /></label>
        <label className={styles.scopeField}>Алиасы<Input value={scopeForm.aliases} placeholder="архитекторы, архитектурная команда" onChange={(event) => setScopeForm({ ...scopeForm, aliases: event.target.value })} /></label>
        {scopeEditor === 'new' && <Checkbox checked={scopeForm.is_all} onChange={(checked) => setScopeForm({ ...scopeForm, is_all: checked, key: checked ? `${scopeForm.scope_type}.all` : `${scopeForm.scope_type}.${slugifyScopeName(scopeForm.name)}` })} label="Общий скоуп типа" description={`Для этого типа будет создан ключ ${scopeForm.scope_type}.all.`} />}
        {saveScope.isError && <p role="alert">Не удалось сохранить скоуп. Проверьте уникальность ключа и соответствие типа.</p>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><Button variant="outline" onClick={() => setScopeEditor(null)}>Отмена</Button><Button disabled={!scopeForm.key || !scopeForm.name.trim() || saveScope.isPending} onClick={() => saveScope.mutate()}>{saveScope.isPending ? 'Сохраняем…' : 'Сохранить'}</Button></div>
      </div>
    </Modal>
    <LifecycleDeleteDialog open={Boolean(scopeToDelete)} action={scopeLifecycleAction} kind="memory_scope" entityId={scopeToDelete?.id ?? ''} entityLabel={scopeToDelete?.name ?? ''} onCancel={() => setScopeToDelete(null)} onSuccess={() => { setScopeToDelete(null); queryClient.invalidateQueries({ queryKey: ['admin', 'memory', 'scopes'] }); queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] }); }} />
    <ConfirmDialog open={confirmMemoryDeactivate} title={`Деактивировать записи памяти (${selectedMemoryIds.size})?`} message="Записи перестанут участвовать в активной памяти." confirmLabel="Деактивировать" cancelLabel="Отмена" variant="warning" confirmLoading={deactivateMemory.isPending} onCancel={() => setConfirmMemoryDeactivate(false)} onConfirm={() => deactivateMemory.mutate()} />
    <ConfirmDialog open={confirmGlossaryAction === 'deactivate'} title={`Деактивировать термины (${selectedGlossaryIds.size})?`} message="Термины останутся в админском списке, но перестанут попадать в глоссарий для поиска и извлечения новых документов." confirmLabel="Деактивировать" cancelLabel="Отмена" variant="warning" confirmLoading={glossaryAction.isPending} onCancel={() => setConfirmGlossaryAction(null)} onConfirm={() => glossaryAction.mutate()} />
    <ConfirmDialog open={confirmGlossaryAction === 'activate'} title={`Активировать термины (${selectedGlossaryIds.size})?`} message="Термины снова станут доступны в глоссарии для поиска и извлечения документов." confirmLabel="Активировать" cancelLabel="Отмена" variant="info" confirmLoading={glossaryAction.isPending} onCancel={() => setConfirmGlossaryAction(null)} onConfirm={() => glossaryAction.mutate()} />
    <ConfirmDialog open={confirmGlossaryAction === 'delete'} title={`Удалить термины (${selectedGlossaryIds.size})?`} message="Термины и связанные с ними определения будут удалены без возможности восстановления." confirmLabel="Удалить" cancelLabel="Отмена" variant="danger" confirmLoading={glossaryAction.isPending} onCancel={() => setConfirmGlossaryAction(null)} onConfirm={() => glossaryAction.mutate()} />
    {activeTab === 'review' && retryableSnapshots.isError && <p role="alert">Не удалось загрузить документы для повторного извлечения.</p>}
    {activeTab === 'review' && (retryableSnapshots.data?.length ?? 0) > 0 && <div style={{ display: 'grid', gap: 10, padding: 12 }}>
      <span>Повторное извлечение учтёт причины отклонения.</span>
      {retryableSnapshots.data?.map((row) => <div key={row.snapshot_id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span>{row.document_title}{row.attempt_number ? ` · попытка ${row.attempt_number}` : ''}</span>
        <Button disabled={reextract.isPending} onClick={() => reextract.mutate(row.snapshot_id)}>Повторить извлечение</Button>
      </div>)}
    </div>}
    {reviewEditor && <MemoryReviewDialog key={reviewEditor.id} candidate={reviewEditor} scopes={memoryScopes ?? []} pending={decision.isPending || saveCandidateTags.isPending}
      onSaveTags={(tags) => saveCandidateTags.mutateAsync({ id: reviewEditor.id, tags })}
      onClose={() => setReviewEditor(null)}
      onApprove={async (body) => { await decision.mutateAsync({ row: reviewEditor, action: 'approve', body }); setReviewEditor(null); }}
      onReject={async (reason) => { await decision.mutateAsync({ row: reviewEditor, action: 'reject', reason }); setReviewEditor(null); }} />}
    {bulkReviewRejectIds && <MemoryBulkRejectDialog ids={bulkReviewRejectIds} onClose={() => setBulkReviewRejectIds(null)}
      onRejected={(ids) => {
        setSelectedReviewIds((current) => new Set([...current].filter((id) => !ids.includes(String(id)))));
        if (ids.length) {
          showSuccess(`Отклонено кандидатов: ${ids.length}`);
          queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
        }
      }} />}
    {scopeProposalEditor && <MemoryScopeProposalDialog key={scopeProposalEditor.id} proposal={scopeProposalEditor}
      pending={scopeDecision.isPending} onClose={() => setScopeProposalEditor(null)}
      onApprove={async (reason) => { await scopeDecision.mutateAsync({ row: scopeProposalEditor, action: 'approve', reason }); }}
      onReject={async (reason) => { await scopeDecision.mutateAsync({ row: scopeProposalEditor, action: 'reject', reason }); }} />}
    </>
  );
}
