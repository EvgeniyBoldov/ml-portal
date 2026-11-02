/**
 * CollectionListPage - Admin page for listing collections.
 * Uses EntityPageV2 and DataTable with server-side search and global client-side filters/sorting.
 *
 * Features:
 * - Search and filtering
 * - Status and metadata display
 * - Row navigation to collection details
 */
import { useEffect, useState } from 'react';
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

const COLLECTION_PAGE_SIZE = 100;
const SEARCH_DEBOUNCE_MS = 300;

export async function fetchAllCollections(search: string): Promise<Collection[]> {
  const firstPage = await collectionsApi.listAll({
    page: 1,
    size: COLLECTION_PAGE_SIZE,
    include_deprecated: true,
    search,
  });
  const items = [...firstPage.items];
  const pageCount = Math.ceil(firstPage.total / COLLECTION_PAGE_SIZE);

  for (let page = 2; page <= pageCount; page += 1) {
    const result = await collectionsApi.listAll({
      page,
      size: COLLECTION_PAGE_SIZE,
      include_deprecated: true,
      search,
    });
    items.push(...result.items);
  }

  if (items.length !== firstPage.total) {
    throw new Error('Не удалось загрузить полный список коллекций');
  }

  return items;
}

export function CollectionListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setDebouncedSearch(search.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [search]);

  const { data: collections = [], isFetching, error, refetch } = useQuery({
    queryKey: qk.collections.adminList({
      include_deprecated: true,
      search: debouncedSearch,
    }),
    queryFn: () => fetchAllCollections(debouncedSearch),
  });

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
      label: 'Название',
      width: 220,
      sortable: true,
      sortValue: (row) => row.name,
      filter: {
        kind: 'text',
        placeholder: 'Название или slug',
        getValue: (row) => `${row.name} ${row.slug}`,
      },
      render: (row) => (
        <div>
          <div className={styles.slug}>{row.slug}</div>
          <div className={styles.name}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      width: 300,
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Поиск в описании',
        getValue: (row) => row.description ?? '',
      },
      render: (row) => (
        <span className={styles.description} title={row.description ?? undefined}>
          {row.description?.trim() || '—'}
        </span>
      ),
    },
    {
      key: 'lifecycle_status',
      label: 'LIFECYCLE',
      width: 150,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: [
          { value: 'active', label: 'Active' },
          { value: 'deprecated', label: 'Deprecated' },
        ],
        getValue: (row) => row.lifecycle_status ?? 'active',
      },
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
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все типы',
        options: [
          { value: 'document', label: 'Документы' },
          { value: 'table', label: 'Таблицы' },
          { value: 'sql', label: 'SQL' },
          { value: 'api', label: 'API' },
          { value: 'template', label: 'Шаблоны' },
        ],
        getValue: (row) => row.collection_type,
      },
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
      sortable: true,
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
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Любой статус',
        options: [
          { value: 'true', label: 'Активна' },
          { value: 'false', label: 'Неактивна' },
        ],
        getValue: (row) => String(row.is_active),
      },
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
      breadcrumbs={[{ label: 'Коллекции' }]}
      headerActions={
        <div className={styles.headerActions}>
          <Input
            placeholder="Поиск коллекций..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
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
        {error && (
          <div role="alert" className={styles.error}>
            Не удалось загрузить все коллекции. Попробуйте снова.
            <Button variant="outline" onClick={() => refetch()}>
              Повторить
            </Button>
          </div>
        )}
        <DataTable
          key={debouncedSearch}
          columns={columns}
          data={collections}
          keyField="id"
          loading={isFetching}
          emptyText="Коллекции не найдены"
          paginated
          pageSize={20}
          pageSizeOptions={[20, 50, 100]}
          onRowClick={(row) => navigate(`/admin/collections/${row.id}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default CollectionListPage;
