/**
 * CollectionsPage - Управление коллекциями (Admin)
 * 
 * Uses DataTable like PromptsListPage
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { 
  AdminPage,
  DataTable, 
  Badge,
  type DataTableColumn,
} from '@/shared/ui';
import { collectionsApi, type Collection } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';

export function CollectionsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: qk.collections.list(),
    queryFn: () => collectionsApi.listAll({ size: 100 }),
  });

  const collections = data?.items ?? [];

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
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>{row.name}</div>
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
      width: 80,
      render: (row) => (
        <Badge variant={row.has_vector_search ? 'success' : 'default'} size="small">
          {row.has_vector_search ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 100,
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'warning'} size="small">
          {row.is_active ? 'Активна' : 'Неактивна'}
        </Badge>
      ),
    },
  ];

  return (
    <AdminPage
      title="Коллекции"
      subtitle="Управление структурированными данными"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск коллекций..."
      actions={[
        {
          label: 'Создать',
          onClick: () => navigate('/admin/collections/new'),
          variant: 'primary',
        },
      ]}
    >
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
    </AdminPage>
  );
}

export default CollectionsPage;
