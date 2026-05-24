/**
 * CollectionsListPage - Admin page for listing Collections
 * 
 * Uses EntityPageV2 + DataTable pattern like PoliciesListPage.
 * Data flows: API types → filtered data → DataTable.
 * No mappers, no intermediate interfaces.
 *
 * Features:
 * - Search and filtering
 * - Status and metadata display
 * - Row navigation to collection details
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { 
  EntityPageV2,
  Tab,
  DataTable, 
  Badge,
  Button,
  Input,
  useToast,
  type DataTableColumn,
} from '@/shared/ui';
import { collectionsApi, type Collection } from '@/shared/api/collections';
import { adminApi } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { ADMIN_ACTION_LABELS, ADMIN_ENTITY_LABELS } from '@/shared/constants/adminLabels';

export function CollectionListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: qk.collections.adminList({ page: 1, size: 100, is_active: undefined }),
    queryFn: () => collectionsApi.listAll({ size: 100, include_deprecated: true }),
  });

  const collections = data?.items ?? [];

  const reindexBatchMutation = useMutation({
    mutationFn: () => adminApi.runRagReindexBatch({ limit: 100, dry_run: false }),
    onSuccess: (res) => {
      showToast(
        `Переиндексация: в очереди ${res.queued}, пропущено ${res.skipped}, ошибок ${res.failed}, проверено ${res.scanned}`,
        res.failed > 0 ? 'warning' : 'success',
      );
    },
    onError: (err: Error) => {
      showToast(err.message || 'Не удалось запустить переиндексацию', 'error');
    },
  });

  const filteredCollections = useMemo(() => {
    if (!search.trim()) return collections;
    const q = search.toLowerCase();
    return collections.filter((c: Collection) =>
      c.name.toLowerCase().includes(q) ||
      c.slug.toLowerCase().includes(q) ||
      c.description?.toLowerCase().includes(q)
    );
  }, [collections, search]);

  const columns: DataTableColumn<Collection>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      width: 250,
      sortable: true,
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'collection_type',
      label: 'ТИП',
      width: 120,
      render: (row) => (
        <Badge tone={row.collection_type === 'document' ? 'warn' : row.collection_type === 'table' ? 'info' : 'neutral'}>
          {row.collection_type === 'document' ? 'Документы' : row.collection_type === 'sql' ? 'SQL' : row.collection_type === 'api' ? 'API' : 'Таблица'}
        </Badge>
      ),
    },
    {
      key: 'fields',
      label: 'ПОЛЯ',
      width: 200,
      render: (row) => {
        const fields = row.fields ?? [];
        return (
          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
            {fields.slice(0, 3).map(f => (
              <Badge key={f.name} tone="neutral">{f.name}</Badge>
            ))}
            {fields.length > 3 && (
              <Badge tone="neutral">+{fields.length - 3}</Badge>
            )}
          </div>
        );
      },
    },
    {
      key: 'total_rows',
      label: 'ЗАПИСЕЙ',
      width: 100,
      render: (row) => row.total_rows?.toLocaleString() ?? '0',
    },
    {
      key: 'vector',
      label: 'ВЕКТОР',
      width: 80,
      render: (row) => (
        <Badge tone={row.has_vector_search ? 'success' : 'neutral'}>
          {row.has_vector_search ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'is_active',
      label: 'АКТИВНОСТЬ',
      width: 120,
      render: (row) => (
        <Badge tone={row.is_active ? 'success' : 'danger'}>
          {row.is_active ? 'Активна' : 'Неактивна'}
        </Badge>
      ),
    },
    {
      key: 'lifecycle_status',
      label: 'LIFECYCLE',
      width: 130,
      render: (row) => (
        <Badge tone={row.lifecycle_status === 'deprecated' ? 'warn' : 'neutral'}>
          {row.lifecycle_status === 'deprecated' ? 'Deprecated' : 'Active'}
        </Badge>
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Коллекции"
      mode="view"
      headerActions={
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Input
            placeholder="Поиск коллекций..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Button
            variant="outline"
            onClick={() => reindexBatchMutation.mutate()}
            disabled={reindexBatchMutation.isPending}
          >
            {reindexBatchMutation.isPending ? 'Запуск...' : ADMIN_ACTION_LABELS.reindexRag}
          </Button>
        </div>
      }
      actionButtons={
        <Button variant="primary" onClick={() => navigate('/admin/collections/new')}>
          {`${ADMIN_ACTION_LABELS.create} ${ADMIN_ENTITY_LABELS.collection}`}
        </Button>
      }
    >
      <Tab title="Коллекции" layout="full">
        <DataTable
          columns={columns}
          data={filteredCollections}
          keyField="id"
          loading={isLoading}
          emptyText="Коллекции не найдены"
          paginated
          pageSize={20}
          onRowClick={(row) => navigate(`/admin/collections/${row.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default CollectionListPage;
