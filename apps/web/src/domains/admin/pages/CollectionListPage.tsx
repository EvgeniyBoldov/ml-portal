/**
 * CollectionListPage - Admin page for listing collections.
 * Uses EntityPageV2 and DataTable with server-side search and pagination.
 *
 * Features:
 * - Search and filtering
 * - Status and metadata display
 * - Row navigation to collection details
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { 
  EntityPageV2,
  Tab,
  DataTable, 
  Badge,
  Button,
  Input,
  LifecycleStatusBadge,
  useToast,
  type DataTableColumn,
} from '@/shared/ui';
import { collectionsApi, type Collection } from '@/shared/api/collections';
import { adminApi } from '@/shared/api/admin';
import { qk } from '@/shared/api/keys';
import { ADMIN_ACTION_LABELS, ADMIN_ENTITY_LABELS } from '@/shared/constants/adminLabels';
import styles from './CollectionListPage.module.css';

export function CollectionListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data, isLoading } = useQuery({
    queryKey: qk.collections.adminList({
      page: currentPage,
      size: pageSize,
      include_deprecated: true,
      search: search.trim(),
    }),
    queryFn: () => collectionsApi.listAll({
      page: currentPage,
      size: pageSize,
      include_deprecated: true,
      search: search.trim(),
    }),
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

  const columns: DataTableColumn<Collection>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      width: 250,
      render: (row) => (
        <div>
          <div className={styles.slug}>{row.slug}</div>
          <div className={styles.name}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'lifecycle_status',
      label: 'LIFECYCLE',
      width: 150,
      render: (row) => (
        <LifecycleStatusBadge
          lifecycleStatus={row.lifecycle_status}
          deprecatedAt={row.deprecated_at}
          retentionDays={row.retention_days}
        />
      ),
    },
    {
      key: 'collection_type',
      label: 'ТИП',
      width: 120,
      render: (row) => (
        <Badge tone={row.collection_type === 'document' ? 'warn' : row.collection_type === 'table' ? 'info' : row.collection_type === 'template' ? 'success' : 'neutral'}>
          {row.collection_type === 'document' ? 'Документы' : row.collection_type === 'sql' ? 'SQL' : row.collection_type === 'api' ? 'API' : row.collection_type === 'template' ? 'Шаблоны' : 'Таблица'}
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
          <div className={styles.fieldBadges}>
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
  ];

  return (
    <EntityPageV2
      title="Коллекции"
      mode="view"
      headerActions={
        <div className={styles.headerActions}>
          <Input
            placeholder="Поиск коллекций..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
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
          data={collections}
          keyField="id"
          loading={isLoading}
          emptyText="Коллекции не найдены"
          paginated
          serverPaginated
          pageSize={pageSize}
          currentPage={currentPage}
          totalItems={data?.total ?? 0}
          pageSizeOptions={[20, 50, 100]}
          onPageChange={setCurrentPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setCurrentPage(1);
          }}
          onRowClick={(row) => navigate(`/admin/collections/${row.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default CollectionListPage;
