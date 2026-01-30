/**
 * PoliciesPage - Политики выполнения агентов
 * 
 * Лимиты: max_steps, max_tool_calls, timeouts, budgets
 * Единый стиль с остальными админ-реестрами.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { policiesApi, type Policy } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage, DataTable, type DataTableColumn, Badge } from '@/shared/ui';

export function PoliciesPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  
  const { data: policies, isLoading, error } = useQuery({
    queryKey: qk.policies.list({}),
    queryFn: () => policiesApi.list({}),
  });

  const filteredPolicies = useMemo(() => {
    if (!policies) return [];
    if (!q.trim()) return policies;
    const query = q.toLowerCase();
    return policies.filter((p) => 
      p.name.toLowerCase().includes(query) ||
      p.slug.toLowerCase().includes(query) ||
      p.description?.toLowerCase().includes(query)
    );
  }, [policies, q]);

  const handleRowClick = (policy: Policy) => {
    navigate(`/admin/policies/${policy.id}`);
  };

  const formatLimit = (value: number | undefined | null, suffix = '') => {
    if (value === undefined || value === null) return '—';
    return `${value.toLocaleString()}${suffix}`;
  };

  const columns: DataTableColumn<Policy>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      width: 280,
      sortable: true,
      render: (policy) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{policy.name}</span>
          <code style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
            {policy.slug}
          </code>
        </div>
      ),
    },
    {
      key: 'max_steps',
      label: 'ШАГИ',
      width: 80,
      render: (policy) => formatLimit(policy.max_steps),
    },
    {
      key: 'max_tool_calls',
      label: 'ВЫЗОВЫ',
      width: 80,
      render: (policy) => formatLimit(policy.max_tool_calls),
    },
    {
      key: 'max_wall_time_ms',
      label: 'ТАЙМАУТ',
      width: 100,
      render: (policy) => policy.max_wall_time_ms 
        ? `${Math.round(policy.max_wall_time_ms / 1000)}с`
        : '—',
    },
    {
      key: 'budget_tokens',
      label: 'ТОКЕНЫ',
      width: 100,
      render: (policy) => formatLimit(policy.budget_tokens),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      sortable: true,
      render: (policy) => (
        <Badge tone={policy.is_active ? 'success' : 'neutral'}>
          {policy.is_active ? 'Активно' : 'Неактивно'}
        </Badge>
      ),
    },
  ];

  return (
    <AdminPage
      title="Политики"
      subtitle="Лимиты выполнения агентов: шаги, вызовы, таймауты, бюджеты"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск политик..."
      actions={[
        {
          label: 'Создать',
          onClick: () => navigate('/admin/policies/new'),
          variant: 'primary',
        },
      ]}
    >
      {error && (
        <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
          Не удалось загрузить политики. Попробуйте снова.
        </div>
      )}

      <DataTable
        columns={columns}
        data={filteredPolicies}
        keyField="id"
        loading={isLoading}
        emptyText="Политики не найдены. Нажмите «Создать» для добавления."
        paginated
        pageSize={20}
        onRowClick={handleRowClick}
      />
    </AdminPage>
  );
}

export default PoliciesPage;
