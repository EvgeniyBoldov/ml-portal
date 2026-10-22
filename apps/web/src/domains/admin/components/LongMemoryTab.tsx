import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Badge, Button, DataTable, type DataTableColumn, type DataTableFilterValue } from '@/shared/ui';
import { adminApi, type LongMemoryAdminDocument } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';

const PAGE_SIZE = 25;

const statusLabel: Record<string, string> = {
  pending: 'В очереди', queued: 'В очереди', running: 'Обработка', completed: 'Готово',
  failed: 'Ошибка', cancelled: 'Отменено', deleted: 'Удалён из LongMemory', not_registered: 'Нет операции',
};

const statusTone = (status: string): 'success' | 'warn' | 'danger' | 'neutral' => {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'pending' || status === 'queued' || status === 'running') return 'warn';
  return 'neutral';
};

export default function LongMemoryTab() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [documentFilter, setDocumentFilter] = useState('');
  const [scopeFilter, setScopeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const scopes = useQuery({ queryKey: qk.admin.memory.scopes(), queryFn: () => adminApi.getMemoryScopes() });
  const activeScopes = (scopes.data ?? []).filter((scope) => scope.lifecycle_status === 'active');
  const documents = useQuery({
    queryKey: qk.admin.memory.longMemoryDocuments({ query: documentFilter || undefined, scope_key: scopeFilter || undefined, status: statusFilter || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    queryFn: () => adminApi.getLongMemoryDocuments({ query: documentFilter || undefined, scope_key: scopeFilter || undefined, status: statusFilter || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
  });

  const columns: DataTableColumn<LongMemoryAdminDocument>[] = [
    {
      key: 'title', label: 'ДОКУМЕНТ', sortable: true,
      filter: { kind: 'text', placeholder: 'Название', getValue: (row) => `${row.title} ${row.filename}` },
      render: (row) => <div><strong>{row.title}</strong><div><small>{row.filename}</small></div></div>,
    },
    {
      key: 'scope_keys', label: 'SCOPE',
      filter: { kind: 'select', placeholder: 'Все scope', options: activeScopes.map((scope) => ({ value: scope.key, label: scope.key })) },
      render: (row) => row.scope_keys.length ? row.scope_keys.join(', ') : 'Без скоупа',
    },
    {
      key: 'status', label: 'СТАТУС', width: 180,
      filter: { kind: 'select', placeholder: 'Все статусы', options: Object.entries(statusLabel).map(([value, label]) => ({ value, label })) },
      render: (row) => <Badge tone={statusTone(row.status)}>{statusLabel[row.status] ?? row.status}</Badge>,
    },
    { key: 'passages', label: 'ФРАГМЕНТЫ', width: 110, align: 'right', render: (row) => row.metrics.unique_passages ?? row.metrics.passages ?? '—' },
    { key: 'entities', label: 'СУЩНОСТИ', width: 105, align: 'right', render: (row) => row.metrics.entities ?? '—' },
    { key: 'triples', label: 'ТРИПЛЕТЫ', width: 105, align: 'right', render: (row) => row.metrics.extracted_triples ?? '—' },
    { key: 'updated_at', label: 'ОБНОВЛЁН', width: 170, render: (row) => row.updated_at ? new Date(row.updated_at).toLocaleString('ru-RU') : '—' },
  ];

  const handleFiltersChange = (filters: Record<string, DataTableFilterValue>) => {
    const nextDocumentFilter = typeof filters.title === 'string' ? filters.title.trim() : '';
    const nextScopeFilter = typeof filters.scope_keys === 'string' ? filters.scope_keys : '';
    const nextStatusFilter = typeof filters.status === 'string' ? filters.status : '';
    setDocumentFilter(nextDocumentFilter);
    setScopeFilter(nextScopeFilter);
    setStatusFilter(nextStatusFilter);
    setPage(1);
  };

  return documents.isError ? <p role="alert">Не удалось загрузить список LongMemory.</p> : <DataTable
    columns={columns}
    data={documents.data?.items ?? []}
    keyField="document_id"
    loading={documents.isLoading}
    emptyText="Документов LongMemory пока нет"
    paginated
    serverPaginated
    pageSize={PAGE_SIZE}
    pageSizeOptions={[PAGE_SIZE]}
    currentPage={page}
    totalItems={documents.data?.total ?? 0}
    onPageChange={setPage}
    onColumnFiltersChange={handleFiltersChange}
    onRowClick={(row) => navigate(`/admin/memory/long-memory/${row.document_id}`)}
  />;
}
