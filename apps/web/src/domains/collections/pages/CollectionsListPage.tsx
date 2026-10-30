/**
 * CollectionsListPage - List of available collections for data management
 *
 * Uses shared UI components: AdminPage, DataTable, Badge
 */
import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { collectionsApi, type Collection } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import { AdminPage, DataTable, Badge, type DataTableColumn } from '@/shared/ui';
import { CollectionLoadError } from '../components/CollectionLoadError';
import styles from './CollectionsListPage.module.css';
import { CollectionWorkspacePicker, useCollectionWorkspace } from '../components/CollectionPresentation';

export default function CollectionsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const workspace = useCollectionWorkspace();

  useEffect(() => {
    const workspaces = workspace.workspaces.data?.items ?? [];
    if (!workspace.tenantId && workspaces.length === 1) workspace.select(workspaces[0].id);
  }, [workspace.tenantId, workspace.workspaces.data, workspace.select]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: qk.collections.appList({ active_only: true, tenant_id: workspace.tenantId || undefined }),
    queryFn: () => collectionsApi.list(true, workspace.tenantId),
    enabled: workspace.isSelected,
    // A collection can be created or reconfigured in the admin surface while
    // this cached view is inactive. Refresh whenever the user re-enters it.
    refetchOnMount: 'always',
  });

  const collections = useMemo(() => data?.items ?? [], [data?.items]);

  const filteredCollections = useMemo(() => {
    if (!search.trim()) return collections;
    const q = search.toLowerCase();
    return collections.filter(c =>
      [
        c.name,
        c.slug,
        c.source?.name,
        c.data_instance?.name,
        c.version?.status === 'published' ? c.description : null,
      ].some(value => value?.toLowerCase().includes(q))
    );
  }, [collections, search]);

  const formatDate = (iso?: string) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '—';
    }
  };

  const columns: DataTableColumn<Collection>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      width: 260,
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Название или slug',
        getValue: row => `${row.name ?? ''} ${row.slug ?? ''}`,
      },
      render: row => (
        <div className={styles['collection-cell']}>
          <span className={styles['collection-name']}>{row.name}</span>
          <span className={styles['collection-slug']}>{row.slug}</span>
          {(row.source?.name || row.data_instance?.name) && (
            <span className={styles['collection-source']}>
              Источник: {row.source?.name || row.data_instance?.name}
            </span>
          )}
          {row.version?.status === 'published' && row.description && (
            <span
              className={styles['collection-description']}
              title={row.description}
            >
              {row.description}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'collection_type',
      label: 'ТИП',
      width: 130,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все типы',
        options: [
          { value: 'document', label: 'Документы' },
          { value: 'table', label: 'Таблица' },
          { value: 'sql', label: 'SQL' },
          { value: 'api', label: 'API' },
          { value: 'template', label: 'Шаблоны' },
        ],
        getValue: row => row.collection_type,
      },
      render: row => (
        <Badge
          className={
            row.collection_type === 'document'
              ? styles['type-document']
              : row.collection_type === 'sql'
                ? styles['type-sql']
                : row.collection_type === 'api'
                  ? styles['type-api']
                  : row.collection_type === 'template'
                    ? styles['type-template']
                    : styles['type-table']
          }
        >
          {row.collection_type === 'document'
            ? 'Документы'
            : row.collection_type === 'sql'
              ? 'SQL'
              : row.collection_type === 'api'
                ? 'API'
                : row.collection_type === 'template'
                  ? 'Шаблоны'
                  : 'Таблица'}
        </Badge>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 110,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: [
          { value: 'true', label: 'Активна' },
          { value: 'false', label: 'Неактивна' },
        ],
        getValue: row => String(row.is_active),
      },
      render: row => (
        <Badge
          className={
            row.is_active ? styles['status-active'] : styles['status-inactive']
          }
        >
          {row.is_active ? 'Активна' : 'Неактивна'}
        </Badge>
      ),
    },
    {
      key: 'total_rows',
      label: 'ЗАПИСЕЙ',
      width: 100,
      sortable: true,
      sortValue: row =>
        row.collection_type === 'api' || row.collection_type === 'sql'
          ? row.count?.value
          : row.total_rows,
      align: 'right',
      filter: {
        kind: 'text',
        placeholder: 'Кол-во',
        getValue: row =>
          row.collection_type === 'api' || row.collection_type === 'sql'
            ? (row.count?.value ?? '')
            : row.total_rows,
      },
      render: row => {
        if (row.collection_type === 'api' || row.collection_type === 'sql') {
          const count = row.count;
          return typeof count?.value === 'number' && count.unit
            ? `${count.value.toLocaleString('ru-RU')} ${count.unit}`
            : '—';
        }
        return row.total_rows?.toLocaleString() ?? '0';
      },
    },
    {
      key: 'created_at',
      label: 'СОЗДАНА',
      width: 160,
      sortable: true,
      filter: {
        kind: 'date-range',
        fromPlaceholder: 'От',
        toPlaceholder: 'До',
        getValue: row => row.created_at,
      },
      render: row => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          {formatDate(row.created_at)}
        </span>
      ),
    },
    {
      key: 'updated_at',
      label: 'ОБНОВЛЕНА',
      width: 160,
      sortable: true,
      filter: {
        kind: 'date-range',
        fromPlaceholder: 'От',
        toPlaceholder: 'До',
        getValue: row => row.updated_at,
      },
      render: row => (
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          {formatDate(row.updated_at)}
        </span>
      ),
    },
  ];

  return (
    <AdminPage
      title="Коллекции данных"
      subtitle="Структурированные данные для AI агентов"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск коллекций..."
      controls={<CollectionWorkspacePicker workspace={workspace} />}
    >
      {!workspace.isSelected ? (
        <p role="status">Выберите рабочую группу, чтобы увидеть доступные коллекции.</p>
      ) : isError ? (
        <CollectionLoadError onRetry={() => void refetch()} />
      ) : (
        <DataTable
          columns={columns}
          data={filteredCollections}
          keyField="id"
          loading={isLoading}
          emptyText="Коллекции не найдены"
          paginated
          pageSize={20}
          onRowClick={row => navigate(`/gpt/collections/${row.slug}?tenant_id=${encodeURIComponent(workspace.tenantId)}`)}
        />
      )}
    </AdminPage>
  );
}
