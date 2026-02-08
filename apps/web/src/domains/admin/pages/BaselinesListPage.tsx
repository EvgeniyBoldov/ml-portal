/**
 * BaselinesListPage - now shows POLICIES (text-based behavioral rules)
 * 
 * Old Baseline list becomes Policy list.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { policiesApi, type Policy } from '@/shared/api/policies';
import { qk } from '@/shared/api/keys';
import {
  AdminPage,
  DataTable,
  type DataTableColumn,
} from '@/shared/ui';
import { RowActions } from '@/shared/ui/RowActions';

export function BaselinesListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: policies = [], isLoading } = useQuery({
    queryKey: qk.policies.list({}),
    queryFn: () => policiesApi.list(),
  });

  const filteredPolicies = useMemo(() => {
    if (!search.trim()) return policies;
    const q = search.toLowerCase();
    return policies.filter(p =>
      p.slug.toLowerCase().includes(q) ||
      p.name.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q)
    );
  }, [policies, search]);

  const columns: DataTableColumn<Policy>[] = [
    {
      key: 'slug',
      label: 'SLUG / ИМЯ',
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.name}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{row.slug}</div>
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
      key: 'updated_at',
      label: 'ОБНОВЛЕНА',
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
            { label: 'Открыть', onClick: () => navigate(`/admin/policies/${row.slug}`) },
            { label: 'Редактировать', onClick: () => navigate(`/admin/policies/${row.slug}?mode=edit`) },
          ]}
        />
      ),
    },
  ];

  return (
    <AdminPage
      title="Политики"
      subtitle="Правила и ограничения поведения агентов"
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Поиск политик..."
      actions={[
        {
          label: 'Создать политику',
          onClick: () => navigate('/admin/policies/new'),
          variant: 'primary',
        },
      ]}
    >
      <DataTable
        columns={columns}
        data={filteredPolicies}
        keyField="id"
        loading={isLoading}
        emptyText="Политики не найдены"
        onRowClick={(row) => navigate(`/admin/policies/${row.slug}`)}
      />
    </AdminPage>
  );
}

export default BaselinesListPage;
