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

  const columns: DataTableColumn<Collection>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      width: 250,
      sortable: true,
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>{row.name}</div>
        </div>
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
              <Badge key={f.name} variant="default" size="small">{f.name}</Badge>
            ))}
            {fields.length > 3 && (
              <Badge variant="default" size="small">+{fields.length - 3}</Badge>
            )}
          </div>
        );
      },
    },
    {
      key: 'row_count',
      label: 'ЗАПИСЕЙ',
      width: 100,
      render: (row) => row.row_count?.toLocaleString() ?? '0',
    },
    {
      key: 'vector',
      label: 'ВЕКТОР',
      width: 100,
      render: (row) => (
        <Badge variant={row.has_vector_search ? 'success' : 'default'}>
          {row.has_vector_search ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 100,
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'warning'}>
          {row.is_active ? 'Активна' : 'Неактивна'}
        </Badge>
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
