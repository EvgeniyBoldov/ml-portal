/**
 * ToolsPage - Реестр групп инструментов
 * 
 * Отображает ToolGroups. Клик по строке → страница группы с инструментами.
 * Использует DataTable как на странице промптов.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolGroupsApi, type ToolGroup } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { 
  AdminPage,
  DataTable,
  type DataTableColumn,
} from '@/shared/ui';

export function ToolsPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  
  const { data: groups = [], isLoading } = useQuery({
    queryKey: qk.toolGroups.list({}),
    queryFn: () => toolGroupsApi.list(),
    staleTime: 60000,
  });

  const filteredGroups = useMemo(() => {
    if (!search.trim()) return groups;
    const q = search.toLowerCase();
    return groups.filter((g: ToolGroup) => 
      g.name.toLowerCase().includes(q) || 
      g.slug.toLowerCase().includes(q) ||
      (g.description?.toLowerCase().includes(q))
    );
  }, [groups, search]);

  const columns: DataTableColumn<ToolGroup>[] = [
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
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (row) => (
        <span style={{ color: 'var(--color-text-muted)' }}>
          {row.description || '—'}
        </span>
      ),
    },
  ];

  return (
    <AdminPage
      title="Группы инструментов"
      subtitle="Группы объединяют инструменты по типу интеграции (RAG, Collections и т.д.)"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск групп..."
    >
      <DataTable
        columns={columns}
        data={filteredGroups}
        keyField="id"
        loading={isLoading}
        emptyText="Группы инструментов не найдены"
        paginated
        pageSize={20}
        onRowClick={(row) => navigate(`/admin/tools/groups/${row.id}`)}
      />
    </AdminPage>
  );
}

export default ToolsPage;
