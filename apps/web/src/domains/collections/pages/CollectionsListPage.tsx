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

export default function CollectionsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: qk.collections.list(),
    queryFn: () => collectionsApi.list(true),
  });

  const collections = data?.items ?? [];

  const filteredCollections = useMemo(() => {
    if (!search.trim()) return collections;
    const q = search.toLowerCase();
    return collections.filter(
      c =>
        c.name.toLowerCase().includes(q) ||
        c.slug.toLowerCase().includes(q) ||
        c.description?.toLowerCase().includes(q)
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
        ],
        getValue: (row) => row.collection_type,
      },
      render: (row) => (
        <Badge
          className={
            row.collection_type === 'document'
              ? styles['type-document']
              : row.collection_type === 'sql'
                ? styles['type-sql']
                : styles['type-table']
          }
        >
          {row.collection_type === 'document' ? 'Документы' : row.collection_type === 'sql' ? 'SQL' : row.collection_type === 'api' ? 'API' : 'Таблица'}
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
      render: (row) => row.total_rows?.toLocaleString() ?? '0',
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
