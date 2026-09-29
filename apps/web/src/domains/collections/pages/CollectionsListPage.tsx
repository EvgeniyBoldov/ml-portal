/**
 * CollectionsListPage - List of available collections for data management
 * 
 * Uses shared UI components: AdminPage, DataTable, Badge
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { collectionsApi, type Collection } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';
import { 
  AdminPage,
  DataTable, 
  Badge,
  type DataTableColumn,
} from '@/shared/ui';
import styles from './CollectionsListPage.module.css';

interface ProjectMemoryCollectionRow {
  id: 'project-memory';
  slug: 'project-memory';
  name: 'Project Memory';
  collection_type: 'memory';
  is_active: true;
  total_rows: number;
  created_at?: string;
  updated_at?: string;
}

interface GlossaryCollectionRow {
  id: 'glossary';
  slug: 'glossary';
  name: 'Глоссарий';
  collection_type: 'memory';
  is_active: true;
  total_rows: number;
  created_at?: string;
  updated_at?: string;
}

interface GlobalMemoryCollectionRow {
  id: 'global-memory';
  slug: 'global-memory';
  name: 'Глобальная память';
  collection_type: 'memory';
  is_active: true;
  total_rows: number;
  created_at?: string;
  updated_at?: string;
}

type CollectionCatalogRow = Collection | ProjectMemoryCollectionRow | GlossaryCollectionRow | GlobalMemoryCollectionRow;

function isProjectMemoryCollection(row: CollectionCatalogRow): row is ProjectMemoryCollectionRow {
  return row.slug === 'project-memory';
}

function isGlossaryCollection(row: CollectionCatalogRow): row is GlossaryCollectionRow {
  return row.slug === 'glossary';
}

export default function CollectionsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: qk.collections.appList({ active_only: true }),
    queryFn: () => collectionsApi.list(true),
    // A collection can be created or reconfigured in the admin surface while
    // this cached view is inactive. Refresh whenever the user re-enters it.
    refetchOnMount: 'always',
  });

  const { data: projectMemory } = useQuery({
    queryKey: qk.collections.projectMemoryOverview(),
    queryFn: () => collectionsApi.getProjectMemoryOverview(),
    refetchOnMount: 'always',
  });

  const { data: glossary } = useQuery({
    queryKey: qk.collections.glossaryOverview(),
    queryFn: () => collectionsApi.getGlossaryOverview(),
    refetchOnMount: 'always',
  });

  const { data: globalMemory } = useQuery({
    queryKey: ['collections', 'global-memory', 'overview'],
    queryFn: () => collectionsApi.getGlobalMemoryOverview({ limit: 1 }),
    refetchOnMount: 'always',
  });

  const collections = useMemo<CollectionCatalogRow[]>(() => {
    const latestUpdate = projectMemory?.projects.reduce<string | undefined>(
      (latest, project) => {
        if (!project.updated_at || (latest && latest >= project.updated_at)) return latest;
        return project.updated_at;
      },
      undefined,
    );
    return [
      {
        id: 'project-memory',
        slug: 'project-memory',
        name: 'Project Memory',
        collection_type: 'memory',
        is_active: true,
        total_rows: projectMemory?.total ?? 0,
        updated_at: latestUpdate,
      },
      {
        id: 'glossary',
        slug: 'glossary',
        name: 'Глоссарий',
        collection_type: 'memory',
        is_active: true,
        total_rows: glossary?.total ?? 0,
        updated_at: glossary?.entries.reduce<string | undefined>(
          (latest, entry) => !latest || latest < entry.updated_at ? entry.updated_at : latest,
          undefined,
        ),
      },
      {
        id: 'global-memory',
        slug: 'global-memory',
        name: 'Глобальная память',
        collection_type: 'memory',
        is_active: true,
        total_rows: globalMemory?.total ?? 0,
      },
      ...(data?.items ?? []),
    ];
  }, [data?.items, glossary, globalMemory, projectMemory]);

  const filteredCollections = useMemo(() => {
    if (!search.trim()) return collections;
    const q = search.toLowerCase();
    return collections.filter(
      c =>
        c.name.toLowerCase().includes(q) ||
        c.slug.toLowerCase().includes(q)
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

  const columns: DataTableColumn<CollectionCatalogRow>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      width: 260,
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Название или slug',
        getValue: (row) => `${row.name ?? ''} ${row.slug ?? ''}`,
      },
      render: (row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{row.name}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{row.slug}</div>
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
          { value: 'memory', label: 'Память' },
        ],
        getValue: (row) => row.collection_type,
      },
      render: (row) => (
        <Badge
          className={
          row.collection_type === 'memory'
              ? styles['type-memory']
              : row.collection_type === 'document'
              ? styles['type-document']
              : row.collection_type === 'sql'
                ? styles['type-sql']
                : row.collection_type === 'template'
                  ? styles['type-template']
                  : styles['type-table']
          }
        >
          {row.collection_type === 'memory'
            ? 'Память'
            : row.collection_type === 'document'
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
        getValue: (row) => String(row.is_active),
      },
      render: (row) => (
        <Badge
          className={row.is_active ? styles['status-active'] : styles['status-inactive']}
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
      align: 'right',
      filter: {
        kind: 'text',
        placeholder: 'Кол-во',
        getValue: (row) => row.total_rows,
      },
      render: (row) => isProjectMemoryCollection(row)
        ? `${row.total_rows.toLocaleString()} фактов`
        : isGlossaryCollection(row)
          ? `${row.total_rows.toLocaleString()} терминов`
          : row.slug === 'global-memory'
            ? `${row.total_rows.toLocaleString()} фактов`
          : row.total_rows?.toLocaleString() ?? '0',
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
        getValue: (row) => row.created_at,
      },
      render: (row) => (
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
        getValue: (row) => row.updated_at,
      },
      render: (row) => (
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
    >
      <DataTable
        columns={columns}
        data={filteredCollections}
        keyField="id"
        loading={isLoading}
        emptyText="Коллекции не найдены"
        paginated
        pageSize={20}
        onRowClick={(row) => navigate(`/gpt/collections/${row.slug}`)}
      />
    </AdminPage>
  );
}
