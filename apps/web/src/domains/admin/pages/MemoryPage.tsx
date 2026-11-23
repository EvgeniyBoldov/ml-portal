import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, ConfirmDialog, DataTable, EntityPageV2, Input, Modal, Tab, LifecycleDeleteDialog } from '@/shared/ui';
import { adminApi, type MemoryScopeAdminItem, type MemoryScopeProposalAdminItem, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import MemoryBulkRejectDialog from '@/domains/admin/components/MemoryBulkRejectDialog';
import MemoryScopeProposalDialog from '@/domains/admin/components/MemoryScopeProposalDialog';
import LongMemoryTab from '@/domains/admin/components/LongMemoryTab';
import LongMemorySearchModal from '@/domains/admin/components/LongMemorySearchModal';
import { scopeColumns, type ScopeTableRow } from '@/domains/admin/components/MemoryScopeTable';
import styles from './MemoryPage.module.css';

const slugifyScopeName = (value: string) => {
  const transliteration: Record<string, string> = { а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch', ы: 'y', э: 'e', ю: 'yu', я: 'ya', ь: '', ъ: '' };
  return value.toLocaleLowerCase().replace(/[а-яё]/g, (char) => transliteration[char] ?? char)
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
};

export default function MemoryPage() {
  useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // DEPRECATED: glossary, approved semantic memory, and candidate review remain
  // in storage/API for historical inspection, but are no longer admin tabs.
  const deprecatedTabs = ['glossary', 'memory', 'review'];
  const requestedTab = searchParams.get('tab') ?? '';
  const initialTab = deprecatedTabs.includes(requestedTab) ? 'scopes' : ['scopes', 'long-memory'].includes(requestedTab) ? requestedTab : 'scopes';
  const [activeTab, setActiveTab] = useState(initialTab);
  const [query, setQuery] = useState('');
  const [memoryScopeType] = useState('');
  const [memoryScopeId] = useState('');
  const [memoryPage] = useState(0);
  const [selectedGlossaryIds, setSelectedGlossaryIds] = useState<Set<string | number>>(new Set());
  const [confirmGlossaryAction, setConfirmGlossaryAction] = useState<'delete' | 'deactivate' | 'activate' | null>(null);
  const [selectedMemoryIds, setSelectedMemoryIds] = useState<Set<string | number>>(new Set());
  const [confirmMemoryDeactivate, setConfirmMemoryDeactivate] = useState(false);
  const [, setSelectedReviewIds] = useState<Set<string | number>>(new Set());
  const [bulkReviewRejectIds, setBulkReviewRejectIds] = useState<string[] | null>(null);
  const [scopeProposalEditor, setScopeProposalEditor] = useState<MemoryScopeProposalAdminItem | null>(null);
  const [scopeEditor, setScopeEditor] = useState<MemoryScopeAdminItem | 'new' | null>(null);
  const [scopeToDelete, setScopeToDelete] = useState<MemoryScopeAdminItem | null>(null);
  const [scopeLifecycleAction, setScopeLifecycleAction] = useState<'delete' | 'restore'>('delete');
  const [isLongMemorySearchOpen, setIsLongMemorySearchOpen] = useState(false);
  const [scopeForm, setScopeForm] = useState({ scope_type: 'project' as MemoryScopeAdminItem['scope_type'], key: '', name: '', aliases: '', is_all: false, project_type: '' });
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const { data: memoryScopes, isLoading: scopesLoading, isError: scopesError } = useQuery({
    queryKey: qk.admin.memory.scopes(), queryFn: () => adminApi.getMemoryScopes(), enabled: activeTab === 'scopes' || activeTab === 'review' || activeTab === 'memory',
  });
  const saveScope = useMutation({
    mutationFn: () => {
      const payload = { ...scopeForm, project_type: scopeForm.scope_type === 'project' && !scopeForm.is_all ? scopeForm.project_type.trim() || null : null, aliases: scopeForm.aliases.split(',').map((value) => value.trim()).filter(Boolean) };
      return scopeEditor === 'new' ? adminApi.createMemoryScope(payload) : adminApi.updateMemoryScope(scopeEditor!.id, payload);
    },
    onSuccess: () => { setScopeEditor(null); queryClient.invalidateQueries({ queryKey: ['admin', 'memory', 'scopes'] }); },
  });
  const { data: glossary } = useQuery({
    queryKey: qk.admin.glossary.all(),
    queryFn: () => adminApi.getGlossary(),
    enabled: activeTab === 'glossary',
  });
  useQuery({
    queryKey: ['admin', 'memory', 'approved', query, memoryScopeType, memoryScopeId, memoryPage],
    queryFn: () => adminApi.getSemanticMemory({
      query: query || undefined,
      scope_type: memoryScopeType || undefined, scope_id: memoryScopeId || undefined,
      limit: 100, offset: memoryPage * 100,
    }),
    enabled: activeTab === 'memory',
  });
  useQuery({
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
  const scopeDecision = useMutation({
    mutationFn: ({ row, action, reason }: { row: MemoryScopeProposalAdminItem; action: 'approve' | 'reject'; reason?: string }) => action === 'approve'
      ? adminApi.approveMemoryScopeProposal(row.id, reason)
      : adminApi.rejectMemoryScopeProposal(row.id, reason ?? ''),
    onSuccess: () => { setScopeProposalEditor(null); queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] }); },
    onError: (error: Error) => showError(error.message || 'Не удалось обработать предложение скоупа'),
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
      queryClient.invalidateQueries({ queryKey: qk.admin.glossary.all() });
      queryClient.invalidateQueries({ queryKey: qk.collections.glossaryAll() });
    },
    onError: (error: Error) => showError(error.message || 'Не удалось изменить выбранные термины'),
  });
  useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return glossary ?? [];
    return (glossary ?? []).filter((row) => [row.canonical_term, ...row.aliases].join(' ').toLocaleLowerCase().includes(needle));
  }, [glossary, query]);
  const openScopeEditor = (row: MemoryScopeAdminItem) => {
    setScopeForm({ scope_type: row.scope_type, key: row.key, name: row.name, aliases: row.aliases.join(', '), is_all: row.is_all, project_type: row.project_type ?? '' });
    setScopeEditor(row);
  };
  const scopeRows: ScopeTableRow[] = [
    ...(memoryScopes ?? []).map((scope): ScopeTableRow => ({ kind: 'published', id: `scope:${scope.id}`, scope_type: scope.scope_type, key: scope.key, name: scope.name, aliases: scope.aliases, status: scope.lifecycle_status, scope })),
    ...(scopeProposals ?? []).map((proposal): ScopeTableRow => ({ kind: 'proposal', id: `proposal:${proposal.id}`, scope_type: proposal.scope_type, key: proposal.proposed_key, name: proposal.name, aliases: proposal.aliases, status: proposal.status, proposal })),
  ];
  return (
    <>
    <EntityPageV2
      title="Мемори"
      defaultTab={initialTab}
      mode="view"
      breadcrumbs={[{ label: 'Мемори' }]}
      onTabChange={(tab) => {
        setActiveTab(tab);
        setQuery('');
        setSearchParams((current) => {
          const next = new URLSearchParams(current);
          next.set('tab', tab);
          return next;
        }, { replace: true });
      }}
      headerActions={null}
    >
      {/* DEPRECATED tabs: glossary, approved semantic memory and review queue are retained in storage/API only. */}
      {/* <Tab title="Глоссарий" id="glossary" layout="full">
        {glossaryError ? <p role="alert">Не удалось загрузить глоссарий.</p> : <DataTable
          columns={glossaryColumns} data={filteredGlossary} keyField="id" loading={glossaryLoading}
          emptyText="Термины не найдены" paginated pageSize={20} selectable onRowClick={(row) => navigate(`/admin/memory/terms/${row.id}`)}
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
      </Tab> */}
      {/* DEPRECATED: historical candidate review is retained in API/storage only. */}
      {/* <Tab title="На проверке" id="review" layout="full">
        {review?.some((row) => row.document_access_scope && row.document_access_scope !== 'global') && <p className={styles.reviewHint}>Термины общего глоссария извлекаются только из документов с глобальным доступом. Документы с доступом к коллекции дают кандидаты памяти, но не термины общего глоссария.</p>}
        {reviewError ? <p role="alert">Не удалось загрузить очередь проверки.</p> : <DataTable
          columns={reviewColumns} data={review ?? []} keyField="id"
          className={styles.reviewTable} selectable selectedKeys={selectedReviewIds} onSelectionChange={setSelectedReviewIds}
          bulkActions={<MemoryActionsMenu items={[{
            label: 'Отклонить выбранные', variant: 'danger', disabled: !selectedReviewCandidates.length,
            onClick: () => setBulkReviewRejectIds(selectedReviewCandidates.map((row) => row.id)),
          }]} />}
          loading={reviewLoading} emptyText="Кандидатов на проверке нет" paginated pageSize={20}
          onRowClick={(row) => navigate(`/admin/memory/review/${row.id}`)} />}
      </Tab> */}
      <Tab title="Скоупы" id="scopes" layout="full" actions={[<Button key="create-scope" onClick={() => { setScopeForm({ scope_type: 'project', key: '', name: '', aliases: '', is_all: false, project_type: '' }); setScopeEditor('new'); }}>Создать скоуп</Button>] }>
        {scopesError || scopeProposalsError ? <p role="alert">Не удалось загрузить скоупы памяти и предложения.</p> : <DataTable columns={scopeColumns({ onReview: setScopeProposalEditor, onEdit: openScopeEditor, onLifecycle: (scope, action) => { setScopeLifecycleAction(action); setScopeToDelete(scope); } })} data={scopeRows} keyField="id" loading={scopesLoading || scopeProposalsLoading} emptyText="Скоупов пока нет" paginated pageSize={20} />}
      </Tab>
      <Tab title="LongMemory" id="long-memory" layout="full" actions={[<Button key="long-memory-search" variant="outline" onClick={() => setIsLongMemorySearchOpen(true)}>Тестовый поиск</Button>]}>
        <LongMemoryTab />
      </Tab>
    </EntityPageV2>
    <Modal open={Boolean(scopeEditor)} title={scopeEditor === 'new' ? 'Новый скоуп памяти' : 'Изменить скоуп памяти'} onClose={() => setScopeEditor(null)}>
      <div style={{ display: 'grid', gap: 12 }}>
        {scopeEditor !== 'new' && <small style={{ color: 'var(--muted)' }}>Slug фиксирует идентичность скоупа; название и алиасы можно изменить.</small>}
        <label className={styles.scopeField}>Slug<Input value={scopeForm.key} disabled={scopeEditor !== 'new'} placeholder="company, nims, dcbox" onChange={(event) => setScopeForm({ ...scopeForm, key: event.target.value })} /></label>
        <label className={styles.scopeField}>Название<Input value={scopeForm.name} onChange={(event) => setScopeForm({ ...scopeForm, name: event.target.value, key: scopeEditor === 'new' ? slugifyScopeName(event.target.value) : scopeForm.key })} /></label>
        <label className={styles.scopeField}>Алиасы<Input value={scopeForm.aliases} placeholder="архитекторы, архитектурная команда" onChange={(event) => setScopeForm({ ...scopeForm, aliases: event.target.value })} /></label>
        <label className={styles.scopeField}>Тип проекта<Input value={scopeForm.project_type} placeholder="Например, platform" onChange={(event) => setScopeForm({ ...scopeForm, project_type: event.target.value })} /></label>
        {saveScope.isError && <p role="alert">Не удалось сохранить скоуп. Проверьте уникальность slug.</p>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><Button variant="outline" onClick={() => setScopeEditor(null)}>Отмена</Button><Button disabled={!scopeForm.key || !scopeForm.name.trim() || saveScope.isPending} onClick={() => saveScope.mutate()}>{saveScope.isPending ? 'Сохраняем…' : 'Сохранить'}</Button></div>
      </div>
    </Modal>
    <LongMemorySearchModal open={isLongMemorySearchOpen} onClose={() => setIsLongMemorySearchOpen(false)} />
    <LifecycleDeleteDialog open={Boolean(scopeToDelete)} action={scopeLifecycleAction} kind="memory_scope" entityId={scopeToDelete?.id ?? ''} entityLabel={scopeToDelete?.name ?? ''} onCancel={() => setScopeToDelete(null)} onSuccess={() => { setScopeToDelete(null); queryClient.invalidateQueries({ queryKey: ['admin', 'memory', 'scopes'] }); queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] }); }} />
    <ConfirmDialog open={confirmMemoryDeactivate} title={`Деактивировать записи памяти (${selectedMemoryIds.size})?`} message="Записи перестанут участвовать в активной памяти." confirmLabel="Деактивировать" cancelLabel="Отмена" variant="warning" confirmLoading={deactivateMemory.isPending} onCancel={() => setConfirmMemoryDeactivate(false)} onConfirm={() => deactivateMemory.mutate()} />
    <ConfirmDialog open={confirmGlossaryAction === 'deactivate'} title={`Деактивировать термины (${selectedGlossaryIds.size})?`} message="Термины останутся в админском списке, но перестанут попадать в глоссарий для поиска и извлечения новых документов." confirmLabel="Деактивировать" cancelLabel="Отмена" variant="warning" confirmLoading={glossaryAction.isPending} onCancel={() => setConfirmGlossaryAction(null)} onConfirm={() => glossaryAction.mutate()} />
    <ConfirmDialog open={confirmGlossaryAction === 'activate'} title={`Активировать термины (${selectedGlossaryIds.size})?`} message="Термины снова станут доступны в глоссарии для поиска и извлечения документов." confirmLabel="Активировать" cancelLabel="Отмена" variant="info" confirmLoading={glossaryAction.isPending} onCancel={() => setConfirmGlossaryAction(null)} onConfirm={() => glossaryAction.mutate()} />
    <ConfirmDialog open={confirmGlossaryAction === 'delete'} title={`Удалить термины (${selectedGlossaryIds.size})?`} message="Термины и связанные с ними определения будут удалены без возможности восстановления." confirmLabel="Удалить" cancelLabel="Отмена" variant="danger" confirmLoading={glossaryAction.isPending} onCancel={() => setConfirmGlossaryAction(null)} onConfirm={() => glossaryAction.mutate()} />
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
