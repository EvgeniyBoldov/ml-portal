import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, DataTable, EntityPageV2, Input, Tab, type DataTableColumn } from '@/shared/ui';
import { adminApi, type AdminGlossaryEntry, type SemanticMemoryAdminItem, type ShadowMemoryCandidate } from '@/shared/api/admin';

const glossaryColumns: DataTableColumn<AdminGlossaryEntry>[] = [
  { key: 'canonical_term', label: 'ТЕРМИН', sortable: true, render: (row) => <div><strong>{row.canonical_term}</strong><div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{row.description || 'Без определения'}</div></div> },
  { key: 'aliases', label: 'АЛИАСЫ', render: (row) => row.aliases.length ? row.aliases.join(', ') : '—' },
  { key: 'scope', label: 'SCOPE', width: 120, render: (row) => <Badge tone="info">{row.scope}</Badge> },
  { key: 'entity_type', label: 'СУЩНОСТЬ', width: 140 },
  { key: 'entity_id', label: 'ENTITY ID', width: 220, render: (row) => row.entity_id || '—' },
  { key: 'tenant_id', label: 'TENANT ID', width: 220, render: (row) => row.tenant_id || '—' },
  { key: 'project_id', label: 'PROJECT ID', width: 220, render: (row) => row.project_id || '—' },
  { key: 'status', label: 'СТАТУС', width: 130, render: (row) => <Badge tone={row.status === 'confirmed' ? 'success' : row.status === 'unconfirmed' ? 'warn' : 'neutral'}>{row.status}</Badge> },
  { key: 'is_active', label: 'АКТИВЕН', width: 100, render: (row) => <Badge tone={row.is_active ? 'success' : 'danger'}>{row.is_active ? 'Да' : 'Нет'}</Badge> },
  { key: 'created_at', label: 'СОЗДАН', width: 170, render: (row) => row.created_at ? new Date(row.created_at).toLocaleString('ru-RU') : '—' },
  { key: 'updated_at', label: 'ОБНОВЛЁН', width: 170, render: (row) => row.updated_at ? new Date(row.updated_at).toLocaleString('ru-RU') : '—' },
];

const projectMemoryColumns: DataTableColumn<SemanticMemoryAdminItem>[] = [
  { key: 'subject', label: 'ЗНАНИЕ', sortable: true, render: (row) => <div><strong>{row.subject}</strong><div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{row.content_text}</div></div> },
  { key: 'item_type', label: 'ТИП', width: 150, render: (row) => <Badge tone="neutral">{row.item_type}</Badge> },
  { key: 'project_id', label: 'PROJECT ID', width: 220, render: (row) => row.project_id || '—' },
  { key: 'state', label: 'СОСТОЯНИЕ', width: 150, render: (row) => <Badge tone={row.state === 'active' ? 'success' : row.state === 'uncertain' ? 'warn' : 'danger'}>{row.state}</Badge> },
  { key: 'confidence', label: 'УВЕРЕННОСТЬ', width: 130, align: 'right', render: (row) => `${Math.round(row.confidence * 100)}%` },
  { key: 'source_count', label: 'ИСТОЧНИКИ', width: 110, align: 'right', render: (row) => row.source_count },
];

const reviewColumns = (onDecision: (id: string, action: 'approve' | 'reject') => void, pending: boolean): DataTableColumn<ShadowMemoryCandidate>[] => [
  { key: 'subject', label: 'КАНДИДАТ', render: (row) => <div><strong>{row.subject}</strong><div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{JSON.stringify(row.content)}</div></div> },
  { key: 'candidate_type', label: 'ТИП', width: 130, render: (row) => <Badge tone="neutral">{row.candidate_type}</Badge> },
  { key: 'scope_candidate', label: 'SCOPE', width: 120, render: (row) => <Badge tone="info">{row.scope_candidate || 'unknown'}</Badge> },
  { key: 'evidence_section_ids', label: 'EVIDENCE', width: 110, render: (row) => row.evidence_section_ids.length },
  { key: 'conflict_ids', label: 'КОНФЛИКТЫ', width: 110, render: (row) => <Badge tone={row.conflict_ids.length ? 'danger' : 'success'}>{row.conflict_ids.length}</Badge> },
  { key: 'actions', label: '', width: 190, render: (row) => <div style={{ display: 'flex', gap: 8 }}><button type="button" disabled={pending || row.conflict_ids.length > 0} onClick={() => onDecision(row.id, 'approve')}>Утвердить</button><button type="button" disabled={pending} onClick={() => onDecision(row.id, 'reject')}>Отклонить</button></div> },
];

export default function MemoryPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('glossary');
  const [query, setQuery] = useState('');
  const queryClient = useQueryClient();
  const { data: glossary, isLoading: glossaryLoading, isError: glossaryError } = useQuery({
    queryKey: ['admin', 'glossary'],
    queryFn: () => adminApi.getGlossary(),
    enabled: activeTab === 'glossary',
  });
  const { data: projectMemory, isLoading: memoryLoading, isError: memoryError } = useQuery({
    queryKey: ['admin', 'memory', 'project', query],
    queryFn: () => adminApi.getSemanticMemory({ scope: 'project', query: query || undefined }),
    enabled: activeTab === 'project-memory',
  });
  const { data: review, isLoading: reviewLoading, isError: reviewError } = useQuery({
    queryKey: ['admin', 'memory', 'staging-review'],
    queryFn: () => adminApi.getShadowMemoryCandidates('needs_review'),
    enabled: activeTab === 'review',
  });
  const decision = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) => action === 'approve'
      ? adminApi.approveShadowMemoryCandidate(id, { scope: 'global' })
      : adminApi.rejectShadowMemoryCandidate(id, 'Rejected by administrator'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'memory', 'staging-review'] }),
  });
  const filteredGlossary = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return glossary ?? [];
    return (glossary ?? []).filter((row) => [row.canonical_term, row.description || '', ...row.aliases, row.entity_type, row.entity_id || '', row.tenant_id || '', row.project_id || ''].join(' ').toLocaleLowerCase().includes(needle));
  }, [glossary, query]);

  return (
    <EntityPageV2
      title="Мемори"
      mode="view"
      onTabChange={setActiveTab}
      headerActions={<Input aria-label="Поиск в активном разделе memory" placeholder="Поиск в текущем разделе" value={query} onChange={(event) => setQuery(event.target.value)} />}
    >
      <Tab title="Глоссарий" id="glossary" layout="full">
        {glossaryError ? <p role="alert">Не удалось загрузить глоссарий.</p> : <DataTable columns={glossaryColumns} data={filteredGlossary} keyField="id" loading={glossaryLoading} emptyText="Термины не найдены" paginated pageSize={20} />}
      </Tab>
      <Tab title="Project Memory" id="project-memory" layout="full">
        {memoryError ? <p role="alert">Не удалось загрузить Project Memory.</p> : <DataTable columns={projectMemoryColumns} data={projectMemory?.items ?? []} keyField="id" loading={memoryLoading} emptyText="Знания проекта не найдены" paginated pageSize={20} onRowClick={(row) => navigate(`/admin/memory/${row.id}`)} />}
      </Tab>
      <Tab title="На проверке" id="review" layout="full">
        {reviewError ? <p role="alert">Не удалось загрузить очередь проверки.</p> : <DataTable columns={reviewColumns((id, action) => decision.mutate({ id, action }), decision.isPending)} data={review ?? []} keyField="id" loading={reviewLoading} emptyText="Кандидатов на проверке нет" paginated pageSize={20} />}
      </Tab>
    </EntityPageV2>
  );
}
