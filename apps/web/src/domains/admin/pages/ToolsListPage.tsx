/**
 * ToolsListPage - Реестр групп инструментов (EntityPageV2)
 * 
 * Отображает ToolGroups. Клик по строке → страница группы с инструментами.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { 
  toolReleasesApi, 
  toolReleasesKeys,
  type ToolGroupListItem,
} from '@/shared/api/toolReleases';
import { 
  EntityPageV2,
  Tab,
} from '@/shared/ui/EntityPage/EntityPageV2';
import { 
  DataTable,
  type DataTableColumn,
  Button,
  Input,
} from '@/shared/ui';

export function ToolsListPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  
  const { data: groups = [], isLoading } = useQuery({
    queryKey: toolReleasesKeys.groupsList(),
    queryFn: () => toolReleasesApi.listGroups(),
    staleTime: 60000,
  });

  const filteredGroups = useMemo(() => {
    if (!search.trim()) return groups;
    const q = search.toLowerCase();
    return groups.filter((g: ToolGroupListItem) => 
      g.name.toLowerCase().includes(q) || 
      g.slug.toLowerCase().includes(q) ||
      (g.description?.toLowerCase().includes(q))
    );
  }, [groups, search]);

  const columns: DataTableColumn<ToolGroupListItem>[] = [
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
      key: 'type',
      label: 'ТИП',
      width: 100,
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
          {row.type || '—'}
        </span>
      ),
    },
    {
      key: 'tools_count',
      label: 'ИНСТРУМЕНТЫ',
      width: 120,
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {row.tools_count || 0}
        </span>
      ),
    },
    {
      key: 'instances_count',
      label: 'ИНСТАНСЫ',
      width: 100,
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {row.instances_count || 0}
        </span>
      ),
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)' }}>
          {row.description || '—'}
        </span>
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Инструменты"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск групп..."
          value={search}
          onChange={setSearch}
        />
      }
          >
      <Tab title="Группы" layout="full">
        <DataTable
          columns={columns}
          data={filteredGroups}
          keyField="id"
          loading={isLoading}
          emptyText="Группы инструментов не найдены"
          paginated
          pageSize={20}
          onRowClick={(row) => navigate(`/admin/tools/groups/${row.slug}`)}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default ToolsListPage;
