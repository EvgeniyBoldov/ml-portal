/**
 * CollectionsListPage - Управление коллекциями (EntityPageV2)
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import { 
  DataTable, 
  Badge,
  Button,
  Input,
  type DataTableColumn,
} from '@/shared/ui';
import { collectionsApi, type Collection } from '@/shared/api/collections';
import { qk } from '@/shared/api/keys';

export function CollectionsListPage() {
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
        <Badge tone={row.has_vector_search ? 'success' : 'neutral'}>
          {row.has_vector_search ? 'Да' : 'Нет'}
        </Badge>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 100,
      render: (row) => (
        <Badge tone={row.is_active ? 'success' : 'warn'}>
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
        <Input
          placeholder="Поиск коллекций..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/collections/new')}>
          Создать
        </Button>
      }
    >
      <Tab 
        title="Коллекции" 
        layout="full"
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
      </Tab>
    </EntityPageV2>
  );
}

export default CollectionsListPage;
