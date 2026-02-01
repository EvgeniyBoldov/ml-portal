/**
 * BaselinesListPage - List of baseline containers
 * 
 * Uses AdminPage layout component
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { baselinesApi, type BaselineListItem, type BaselineScope } from '@/shared/api/baselines';
import { qk } from '@/shared/api/keys';
import { 
  AdminPage,
  DataTable, 
  Badge,
  type DataTableColumn,
} from '@/shared/ui';
import { RowActions } from '@/shared/ui/RowActions';

const SCOPE_CONFIG: Record<BaselineScope, { label: string; variant: 'default' | 'success' | 'warning' }> = {
  default: { label: 'Default', variant: 'default' },
  tenant: { label: 'Tenant', variant: 'warning' },
  user: { label: 'User', variant: 'success' },
};

const STATUS_CONFIG = {
  active: { label: 'Активен', variant: 'success' as const },
  draft: { label: 'Черновик', variant: 'warning' as const },
  none: { label: 'Нет версий', variant: 'default' as const },
  inactive: { label: 'Неактивен', variant: 'default' as const },
};

export function BaselinesListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: baselines = [], isLoading } = useQuery({
    queryKey: qk.baselines.list({}),
    queryFn: () => baselinesApi.list(),
  });

  // Filter by search
  const filteredBaselines = useMemo(() => {
    if (!search.trim()) return baselines;
    const q = search.toLowerCase();
    return baselines.filter(b => 
      b.slug.toLowerCase().includes(q) || 
      b.name.toLowerCase().includes(q) ||
      b.description?.toLowerCase().includes(q)
    );
  }, [baselines, search]);

  const columns: DataTableColumn<BaselineListItem>[] = [
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
      key: 'scope',
      label: 'SCOPE',
      width: 100,
      render: (row) => {
        const config = SCOPE_CONFIG[row.scope];
        return <Badge variant={config.variant}>{config.label}</Badge>;
      },
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
        if (!row.is_active) {
          return <Badge variant="default">Неактивен</Badge>;
        }
        const status = row.active_version ? 'active' : row.versions_count > 0 ? 'draft' : 'none';
        const config = STATUS_CONFIG[status];
        return <Badge variant={config.variant}>{config.label}</Badge>;
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
            { label: 'Открыть', onClick: () => navigate(`/admin/baselines/${row.slug}`) },
            { label: 'Редактировать', onClick: () => navigate(`/admin/baselines/${row.slug}?mode=edit`) },
          ]}
        />
      ),
    },
  ];

  return (
    <AdminPage
      title="Бейслайны"
      subtitle="Ограничения и запреты для агентов"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск бейслайнов..."
      actions={[
        { 
          label: 'Создать бейслайн', 
          onClick: () => navigate('/admin/baselines/new'), 
          variant: 'primary',
        },
      ]}
    >
      <DataTable
        columns={columns}
        data={filteredBaselines}
        keyField="id"
        loading={isLoading}
        emptyText="Бейслайны не найдены"
        onRowClick={(row) => navigate(`/admin/baselines/${row.slug}`)}
      />
    </AdminPage>
  );
}

export default BaselinesListPage;
