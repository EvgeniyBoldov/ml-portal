/**
 * RbacListPage - List of RBAC policies (named rule sets)
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { rbacApi, type RbacPolicy } from '@/shared/api/rbac';
import { qk } from '@/shared/api/keys';
import { AdminPage, DataTable, type DataTableColumn, Badge } from '@/shared/ui';

export function RbacListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: policies = [], isLoading } = useQuery({
    queryKey: qk.rbac.list({}),
    queryFn: () => rbacApi.listPolicies(),
  });

  const filtered = useMemo(() => {
    if (!search.trim()) return policies;
    const q = search.toLowerCase();
    return policies.filter(
      (p) =>
        p.slug.toLowerCase().includes(q) ||
        p.name.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q)
    );
  }, [policies, search]);

  const columns: DataTableColumn<RbacPolicy>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      render: (row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{row.name}</span>
          <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {row.slug}
          </code>
        </div>
      ),
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (row) => (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          {row.description || '—'}
        </span>
      ),
    },
    {
      key: 'rules_count',
      label: 'ПРАВИЛА',
      width: 100,
      render: (row) => (
        <Badge tone="neutral" size="small">
          {row.rules_count}
        </Badge>
      ),
    },
    {
      key: 'updated_at',
      label: 'ОБНОВЛЕНО',
      width: 140,
      render: (row) =>
        new Date(row.updated_at).toLocaleDateString('ru-RU', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
        }),
    },
  ];

  return (
    <AdminPage
      title="RBAC"
      subtitle="Наборы правил доступа к ресурсам платформы"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск наборов..."
      actions={[
        {
          label: 'Создать набор',
          onClick: () => navigate('/admin/rbac/new'),
          variant: 'primary',
        },
      ]}
    >
      <DataTable
        columns={columns}
        data={filtered}
        keyField="id"
        loading={isLoading}
        emptyText="Наборы RBAC не найдены. Нажмите «Создать набор» для добавления."
        onRowClick={(row) => navigate(`/admin/rbac/${row.slug}`)}
      />
    </AdminPage>
  );
}

export default RbacListPage;
