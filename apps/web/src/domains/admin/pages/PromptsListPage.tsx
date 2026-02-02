/**
 * PromptsListPage - List of prompt containers
 * 
 * Uses AdminPage layout component
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { promptsApi, type PromptListItem } from '@/shared/api/prompts';
import { qk } from '@/shared/api/keys';
import { 
  AdminPage,
  DataTable, 
  Badge,
  type DataTableColumn,
} from '@/shared/ui';
import { RowActions } from '@/shared/ui/RowActions';

const STATUS_CONFIG = {
  active: { label: 'Активна', variant: 'success' as const },
  draft: { label: 'Черновик', variant: 'warning' as const },
  none: { label: 'Нет версий', variant: 'neutral' as const },
};

export function PromptsListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: prompts = [], isLoading } = useQuery({
    queryKey: qk.prompts.list({}),
    queryFn: () => promptsApi.listPrompts(),
  });

  // Filter by search
  const filteredPrompts = useMemo(() => {
    if (!search.trim()) return prompts;
    const q = search.toLowerCase();
    return prompts.filter(p => 
      p.slug.toLowerCase().includes(q) || 
      p.name.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q)
    );
  }, [prompts, search]);

  const columns: DataTableColumn<PromptListItem>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.slug}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>{row.name}</div>
        </div>
      ),
    },
    {
      key: 'versions',
      label: 'ВЕРСИИ',
      width: 100,
      render: (row) => (
        <span>
          {row.active_version ? `v${row.active_version}` : '—'} 
          {row.versions_count > 0 && <span style={{ color: 'var(--color-text-muted)' }}> ({row.versions_count})</span>}
        </span>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 120,
      render: (row) => {
        const status = row.active_version ? 'active' : row.versions_count > 0 ? 'draft' : 'none';
        const config = STATUS_CONFIG[status];
        return <Badge tone={config.variant}>{config.label}</Badge>;
      },
    },
    {
      key: 'updated_at',
      label: 'ОБНОВЛЁН',
      width: 140,
      render: (row) => new Date(row.updated_at).toLocaleDateString('ru-RU'),
    },
    {
      key: 'actions',
      label: '',
      width: 60,
      align: 'right',
      render: (row) => (
        <RowActions
          actions={[
            { label: 'Открыть', onClick: () => navigate(`/admin/prompts/${row.slug}`) },
            { label: 'Редактировать', onClick: () => navigate(`/admin/prompts/${row.slug}`) },
          ]}
        />
      ),
    },
  ];

  return (
    <AdminPage
      title="Промпты"
      subtitle="Управление системными промптами и бейслайнами"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск промптов..."
      actions={[
        { 
          label: 'Создать промпт', 
          onClick: () => navigate('/admin/prompts/new'), 
          variant: 'primary',
        },
      ]}
    >
      <DataTable
        columns={columns}
        data={filteredPrompts}
        keyField="id"
        loading={isLoading}
        emptyText="Промпты не найдены"
        onRowClick={(row) => navigate(`/admin/prompts/${row.slug}`)}
      />
    </AdminPage>
  );
}

export default PromptsListPage;
