import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Checkbox, ConfirmDialog, DataTable, EntityPageV2, Input, Modal, Select, Tab, LifecycleDeleteDialog, type DataTableColumn } from '@/shared/ui';
import { adminApi, type AdminGlossaryTerm, type MemoryScopeAdminItem, type SemanticMemoryAdminItem, type ShadowMemoryCandidate } from '@/shared/api/admin';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import MemoryReviewDialog, { type MemoryApproval } from '@/domains/admin/components/MemoryReviewDialog';
import MemoryActionsMenu from '@/domains/admin/components/MemoryActionsMenu';
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

const candidateTypeLabels: Record<string, string> = {
  term: 'Термин', description: 'Описание', relationship: 'Связь', rule: 'Правило',
  constraint: 'Ограничение', procedure: 'Процедура', decision: 'Решение',
};

const candidatePayloadContent = (row: ShadowMemoryCandidate): Record<string, unknown> => {
  if (row.content && Object.keys(row.content).length) return row.content;
  try {
    const parsed: unknown = JSON.parse(row.content_text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
};

const candidateContent = (row: ShadowMemoryCandidate): string => {
  const payload = candidatePayloadContent(row);
  const content = Object.keys(payload).length > 0 ? payload : null;
  if (content) {
    const primaryKeys = ['summary', 'definition', 'statement', 'decision', 'goal', 'text', 'value'];
    const entries = Object.entries(content).sort(([left], [right]) => {
      const leftIndex = primaryKeys.indexOf(left);
      const rightIndex = primaryKeys.indexOf(right);
      return (leftIndex < 0 ? Number.MAX_SAFE_INTEGER : leftIndex) - (rightIndex < 0 ? Number.MAX_SAFE_INTEGER : rightIndex);
    });
    const values = entries.flatMap(([key, value]) => {
      if (value === null || value === undefined || value === '') return [];
      const rendered = Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : String(value);
      return [primaryKeys.includes(key) && typeof value === 'string' ? rendered : `${key}: ${rendered}`];
    });
    if (values.length) return values.slice(0, 3).join(' · ');
  }
  if (row.aliases.length) return `Алиасы: ${row.aliases.join(', ')}`;
  if (row.candidate_type === 'term') return 'Определение не указано';
  if (row.related_project_keys.length) return `Проекты: ${row.related_project_keys.join(', ')}`;
  return 'Содержание не извлечено';
};

const candidateConfidence = (value: number): string => {
  if (!Number.isFinite(value) || value < 0 || value > 1) return '—';
  return `${Math.round(value * 100)}%${value >= 1 ? ' · максимум модели' : ''}`;
};

const reviewColumns: DataTableColumn<ShadowMemoryCandidate>[] = [
  { key: 'subject', label: 'КАНДИДАТ / ЗНАЧЕНИЕ', sortable: true, sortValue: (row) => row.subject, filter: { kind: 'text', placeholder: 'Кандидат или содержимое', getValue: (row) => `${row.subject} ${candidateContent(row)}` }, render: (row) => <div><strong>{row.subject}</strong><div style={{ color: row.content_valid ? 'var(--muted)' : 'var(--danger)', fontSize: '0.8rem', whiteSpace: 'normal' }}>{candidateContent(row)}</div></div> },
  { key: 'candidate_type', label: 'ТИП', width: 150, sortable: true, filter: { kind: 'text', placeholder: 'Тип' }, render: (row) => <Badge tone="neutral">{candidateTypeLabels[row.candidate_type] ?? row.candidate_type}</Badge> },
  { key: 'content_valid', label: 'ФОРМАТ', width: 150, render: (row) => row.content_valid ? <Badge tone="success">корректный</Badge> : <Badge tone="danger" title={row.content_error ?? undefined}>неполный</Badge> },
  { key: 'scope_candidate', label: 'ОБЛАСТЬ', width: 240, sortable: true, filter: { kind: 'select', placeholder: 'Все области', options: ['global', 'scoped', 'project', 'multi_project', 'unknown'].map((value) => ({ value, label: value })), getValue: (row) => row.scope_candidate || 'unknown' }, render: (row) => <div><Badge tone="info">{row.scope_candidate || 'unknown'}</Badge>{row.scope_keys.length > 0 && <div style={{ fontSize: '0.8rem' }}>Применимость: {row.scope_keys.join(', ')}</div>}{row.mentioned_scope_keys.length > 0 && <div style={{ fontSize: '0.8rem' }}>Упомянуты: {row.mentioned_scope_keys.join(', ')}</div>}{row.unmatched_scope_names.length > 0 && <div style={{ fontSize: '0.8rem' }}>Нет в каталоге: {row.unmatched_scope_names.join(', ')}</div>}</div> },
  { key: 'evidence_section_ids', label: 'ИСТОЧНИКИ', width: 130, align: 'right', sortable: true, sortValue: (row) => row.evidence_section_ids.length, render: (row) => row.evidence_section_ids.length },
  { key: 'conflict_ids', label: 'КОНФЛИКТЫ', width: 130, align: 'right', sortable: true, sortValue: (row) => row.conflict_ids.length, filter: { kind: 'select', placeholder: 'Все', options: [{ value: 'yes', label: 'Есть' }, { value: 'no', label: 'Нет' }], getValue: (row) => row.conflict_ids.length ? 'yes' : 'no' }, render: (row) => <Badge tone={row.conflict_ids.length ? 'danger' : 'success'}>{row.conflict_ids.length}</Badge> },
  { key: 'extraction_confidence', label: 'УВЕРЕННОСТЬ', width: 170, align: 'right', sortable: true, filter: { kind: 'select', placeholder: 'Любая', options: [{ value: 'high', label: '≥ 80%' }, { value: 'medium', label: '50–79%' }, { value: 'low', label: '< 50%' }], getValue: (row) => row.extraction_confidence >= 0.8 ? 'high' : row.extraction_confidence >= 0.5 ? 'medium' : 'low' }, render: (row) => <span title="Самооценка экстрактора, не подтверждение администратора">{candidateConfidence(row.extraction_confidence)}</span> },
];

export default function MemoryPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('glossary');
  const [query, setQuery] = useState('');
  const [memoryScopeType, setMemoryScopeType] = useState('');
  const [memoryScopeId, setMemoryScopeId] = useState('');
  const [memoryPage, setMemoryPage] = useState(0);
  const [selectedGlossaryIds, setSelectedGlossaryIds] = useState<Set<string | number>>(new Set());
  const [confirmGlossaryAction, setConfirmGlossaryAction] = useState<'delete' | 'deactivate' | 'activate' | null>(null);
  const [selectedMemoryIds, setSelectedMemoryIds] = useState<Set<string | number>>(new Set());
  const [confirmMemoryDeactivate, setConfirmMemoryDeactivate] = useState(false);
  const [reviewPage, setReviewPage] = useState(0);
  const [reviewType, setReviewType] = useState('');
  const [selectedReviewIds, setSelectedReviewIds] = useState<Set<string | number>>(new Set());
  const [confirmReviewAction, setConfirmReviewAction] = useState<'delete' | 'deactivate' | 'reject' | null>(null);
  const [reviewQueue, setReviewQueue] = useState<string[]>([]);
  const [scopeEditor, setScopeEditor] = useState<MemoryScopeAdminItem | 'new' | null>(null);
  const [scopeToDelete, setScopeToDelete] = useState<MemoryScopeAdminItem | null>(null);
  const [scopeLifecycleAction, setScopeLifecycleAction] = useState<'delete' | 'restore'>('delete');
  const [reviewEditor, setReviewEditor] = useState<ShadowMemoryCandidate | null>(null);
  const [scopeForm, setScopeForm] = useState({ scope_type: 'team' as MemoryScopeAdminItem['scope_type'], key: '', name: '', aliases: '', is_all: false });
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const { data: memoryScopes, isLoading: scopesLoading, isError: scopesError } = useQuery({
    queryKey: ['admin', 'memory', 'scopes'], queryFn: () => adminApi.getMemoryScopes(), enabled: activeTab === 'scopes' || activeTab === 'review' || activeTab === 'memory',
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
    queryKey: ['admin', 'memory', 'staging-review', reviewType, reviewPage],
    queryFn: () => adminApi.getShadowMemoryCandidates('pending', { candidate_type: reviewType || undefined, limit: 101, offset: reviewPage * 100 }),
    enabled: activeTab === 'review',
  });
  const decision = useMutation({
    mutationFn: ({ row, action, body }: { row: ShadowMemoryCandidate; action: 'approve' | 'reject'; body?: MemoryApproval }) => action === 'approve'
      ? adminApi.approveShadowMemoryCandidate(row.id, body ?? {})
      : adminApi.rejectShadowMemoryCandidate(row.id, 'Rejected by administrator'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'glossary'] });
      queryClient.invalidateQueries({ queryKey: ['collections', 'glossary', 'overview'] });
    },
  });
  const approveSelected = useMutation({
    mutationFn: () => adminApi.bulkApproveShadowTerms([...selectedReviewIds].map(String)),
    onSuccess: ({ approved_ids, review_ids }) => {
      setSelectedReviewIds(new Set(review_ids));
      setReviewQueue(review_ids);
      setReviewEditor((review ?? []).find((row) => row.id === review_ids[0]) ?? null);
      if (approved_ids.length) showSuccess(`Утверждено терминов: ${approved_ids.length}`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'glossary'] });
      queryClient.invalidateQueries({ queryKey: ['collections', 'glossary', 'overview'] });
    },
    onError: (error: Error) => showError(error.message || 'Не удалось утвердить выбранные записи'),
  });
  const bulkReviewAction = useMutation({
    mutationFn: async (action: 'delete' | 'deactivate' | 'reject') => {
      const ids = [...selectedReviewIds].map(String);
      if (action === 'delete') return adminApi.deleteShadowMemoryCandidates(ids);
      if (action === 'deactivate') return adminApi.deactivateShadowMemoryCandidates(ids);
      await Promise.all(ids.map((id) => adminApi.rejectShadowMemoryCandidate(id, 'Rejected by administrator')));
      return { changed: ids.length };
    },
    onSuccess: (result) => {
      setSelectedReviewIds(new Set());
      setConfirmReviewAction(null);
      showSuccess(`${confirmReviewAction === 'delete' ? 'Удалено' : confirmReviewAction === 'deactivate' ? 'Деактивировано' : 'Отклонено'} кандидатов: ${result.changed}`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'memory'] });
    },
    onError: (error: Error) => showError(error.message || 'Не удалось обработать выбранных кандидатов'),
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
  const scopeColumns: DataTableColumn<MemoryScopeAdminItem>[] = [
    { key: 'scope_type', label: 'ТИП', width: 130, sortable: true, render: (row) => <Badge tone="info">{row.scope_type}</Badge> },
    { key: 'key', label: 'КЛЮЧ', sortable: true, filter: { kind: 'text', placeholder: 'Ключ' }, render: (row) => <code>{row.key}</code> },
    { key: 'name', label: 'НАЗВАНИЕ', sortable: true, filter: { kind: 'text', placeholder: 'Название' }, render: (row) => <div><strong>{row.name}</strong>{row.is_all && <div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>Все {row.scope_type === 'team' ? 'подразделения' : row.scope_type === 'project' ? 'проекты' : 'продукты'}</div>}</div> },
    { key: 'aliases', label: 'АЛИАСЫ', render: (row) => row.aliases.join(', ') || '—' },
    { key: 'lifecycle_status', label: 'СТАТУС', width: 140, render: (row) => <Badge tone={row.lifecycle_status === 'active' ? 'success' : 'warn'}>{row.lifecycle_status === 'active' ? 'активен' : `удалится через ${row.retention_days} дн.`}</Badge> },
    { key: 'actions', label: '', width: 80, render: (row) => <MemoryActionsMenu label="⋯" ariaLabel={`Действия со скоупом ${row.name}`}
      items={row.lifecycle_status === 'active' ? [
        { label: 'Изменить', onClick: () => openScopeEditor(row) },
        { label: 'Удалить', variant: 'danger', onClick: () => { setScopeLifecycleAction('delete'); setScopeToDelete(row); } },
      ] : [{ label: 'Восстановить', onClick: () => { setScopeLifecycleAction('restore'); setScopeToDelete(row); } }]} /> },
  ];

  return (
    <>
    <EntityPageV2
      title="Мемори"
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
        <div className={styles.filterBar}>
          <label className={styles.scopeField}>Тип кандидата
            <Select value={reviewType} options={[{ value: '', label: 'Все типы' }, ...['term', 'description', 'relationship', 'rule', 'constraint', 'procedure', 'decision'].map((value) => ({ value, label: value }))]} onChange={(value) => { setReviewType(value); setReviewPage(0); setSelectedReviewIds(new Set()); }} />
          </label>
        </div>
        {reviewError ? <p role="alert">Не удалось загрузить очередь проверки.</p> : <DataTable
          key={`${reviewPage}:${reviewType}`} columns={reviewColumns} data={(review ?? []).slice(0, 100)} keyField="id"
          loading={reviewLoading} emptyText="Кандидатов на проверке нет" paginated pageSize={20} selectable
          selectedKeys={selectedReviewIds} onSelectionChange={setSelectedReviewIds}
          bulkActions={<div className={styles.selectionActions}>
            <Button size="sm" disabled={approveSelected.isPending || decision.isPending || bulkReviewAction.isPending}
              onClick={() => approveSelected.mutate()}>Утвердить</Button>
            <MemoryActionsMenu disabled={bulkReviewAction.isPending || approveSelected.isPending} items={[
              { label: 'Отклонить', onClick: () => setConfirmReviewAction('reject') },
              { label: 'Деактивировать', onClick: () => setConfirmReviewAction('deactivate') },
              { label: 'Удалить', variant: 'danger', onClick: () => setConfirmReviewAction('delete') },
            ]} />
          </div>} />}
        {(reviewPage > 0 || (review?.length ?? 0) > 100) && <div className={styles.pager}>
          <Button size="sm" variant="outline" disabled={reviewPage === 0} onClick={() => { setReviewPage(reviewPage - 1); setSelectedReviewIds(new Set()); }}>Назад</Button>
          <span>Страница {reviewPage + 1}</span>
          <Button size="sm" variant="outline" disabled={(review?.length ?? 0) <= 100} onClick={() => { setReviewPage(reviewPage + 1); setSelectedReviewIds(new Set()); }}>Далее</Button>
        </div>}
      </Tab>
      <Tab title="Скоупы" id="scopes" layout="full" actions={[<Button key="create-scope" onClick={() => { setScopeForm({ scope_type: 'team', key: '', name: '', aliases: '', is_all: false }); setScopeEditor('new'); }}>Создать скоуп</Button>]}>
        {scopesError ? <p role="alert">Не удалось загрузить скоупы памяти.</p> : <DataTable columns={scopeColumns} data={memoryScopes ?? []} keyField="id" loading={scopesLoading} emptyText="Скоупов пока нет" paginated pageSize={20} onRowClick={(row) => { if (row.lifecycle_status === 'active') openScopeEditor(row); }} />}
      </Tab>
    </EntityPageV2>
    <Modal open={Boolean(scopeEditor)} title={scopeEditor === 'new' ? 'Новый скоуп памяти' : 'Изменить скоуп памяти'} onClose={() => setScopeEditor(null)}>
      <div style={{ display: 'grid', gap: 12 }}>
        <label className={styles.scopeField}>Тип<Select options={[{ value: 'product', label: 'product' }, { value: 'project', label: 'project' }, { value: 'team', label: 'team' }]} value={scopeForm.scope_type} disabled={scopeEditor !== 'new'} onChange={(value) => { const nextType = value as MemoryScopeAdminItem['scope_type']; setScopeForm({ ...scopeForm, scope_type: nextType, key: scopeForm.is_all ? `${nextType}.all` : `${nextType}.${slugifyScopeName(scopeForm.name)}` }); }} /></label>
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
    <ConfirmDialog open={confirmReviewAction !== null} title={`${confirmReviewAction === 'delete' ? 'Удалить' : confirmReviewAction === 'deactivate' ? 'Деактивировать' : 'Отклонить'} кандидатов (${selectedReviewIds.size})?`} message={confirmReviewAction === 'delete' ? 'Выбранные записи извлечения будут удалены без возможности восстановления.' : confirmReviewAction === 'deactivate' ? 'Кандидаты будут помечены неактивными и исчезнут из очереди проверки.' : 'Кандидаты будут отклонены и убраны из очереди проверки.'} confirmLabel={confirmReviewAction === 'delete' ? 'Удалить' : confirmReviewAction === 'deactivate' ? 'Деактивировать' : 'Отклонить'} cancelLabel="Отмена" variant={confirmReviewAction === 'deactivate' ? 'warning' : 'danger'} confirmLoading={bulkReviewAction.isPending} onCancel={() => setConfirmReviewAction(null)} onConfirm={() => confirmReviewAction && bulkReviewAction.mutate(confirmReviewAction)} />
    {reviewEditor && <MemoryReviewDialog key={reviewEditor.id} candidate={reviewEditor} scopes={memoryScopes ?? []} pending={decision.isPending} onClose={() => { setReviewEditor(null); setReviewQueue([]); }} onApprove={async (body) => { await decision.mutateAsync({ row: reviewEditor, action: 'approve', body }); const remaining = reviewQueue.slice(1); setReviewQueue(remaining); setReviewEditor((review ?? []).find((row) => row.id === remaining[0]) ?? null); if (!remaining.length) setSelectedReviewIds(new Set()); }} />}
    </>
  );
}
