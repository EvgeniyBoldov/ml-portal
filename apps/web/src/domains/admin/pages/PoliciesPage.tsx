/**
 * PoliciesPage - Политики доступа для агентов
 * 
 * Единый стиль с остальными админ-реестрами.
 * Клик по строке → View страница, редактирование через кнопку на View.
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { permissionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import { AdminPage } from '@/shared/ui';
import Badge from '@/shared/ui/Badge';
import { AdminTable, type AdminTableColumn } from '@/shared/ui/AdminTable';

interface Policy {
  id: string;
  name?: string;
  allowed_tools?: string[];
  denied_tools?: string[];
  is_active: boolean;
}

export function PoliciesPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  
  const { data: policies, isLoading, error } = useQuery({
    queryKey: qk.permissions.list({}),
    queryFn: () => permissionsApi.list({}),
  });

  const filteredPolicies = useMemo(() => {
    if (!policies) return [];
    if (!q.trim()) return policies;
    const query = q.toLowerCase();
    return policies.filter((p: Policy) => 
      p.name?.toLowerCase().includes(query) ||
      p.id.toLowerCase().includes(query) ||
      p.allowed_tools?.some(t => t.toLowerCase().includes(query)) ||
      p.denied_tools?.some(t => t.toLowerCase().includes(query))
    );
  }, [policies, q]);

  const handleRowClick = (policy: Policy) => {
    navigate(`/admin/policies/${policy.id}`);
  };

  const columns: AdminTableColumn<Policy>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      sortable: true,
      render: (policy) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>
            {policy.name || `Ограничение #${policy.id.slice(0, 8)}`}
          </span>
          <code style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
            {policy.id.slice(0, 8)}...
          </code>
        </div>
      ),
    },
    {
      key: 'allowed_tools',
      label: 'РАЗРЕШЁННЫЕ',
      render: (policy) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {policy.allowed_tools?.slice(0, 3).map((tool: string) => (
            <Badge key={tool} tone="success" size="small">{tool}</Badge>
          ))}
          {(policy.allowed_tools?.length || 0) > 3 && (
            <Badge tone="neutral" size="small">+{policy.allowed_tools!.length - 3}</Badge>
          )}
          {!policy.allowed_tools?.length && <span style={{ color: 'var(--muted)' }}>Все</span>}
        </div>
      ),
    },
    {
      key: 'denied_tools',
      label: 'ЗАПРЕЩЁННЫЕ',
      render: (policy) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {policy.denied_tools?.slice(0, 2).map((tool: string) => (
            <Badge key={tool} tone="danger" size="small">{tool}</Badge>
          ))}
          {(policy.denied_tools?.length || 0) > 2 && (
            <Badge tone="neutral" size="small">+{policy.denied_tools!.length - 2}</Badge>
          )}
          {!policy.denied_tools?.length && <span style={{ color: 'var(--muted)' }}>—</span>}
        </div>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      sortable: true,
      render: (policy) => (
        <Badge tone={policy.is_active ? 'success' : 'neutral'} size="small">
          {policy.is_active ? 'Активно' : 'Неактивно'}
        </Badge>
      ),
    },
  ];

  return (
    <AdminPage
      title="Политики"
      subtitle="Настройка доступа к инструментам для агентов"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск ограничений..."
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

      <AdminTable
        columns={columns}
        data={filteredPolicies}
        keyField="id"
        loading={isLoading}
        emptyText="Политики не найдены. Нажмите «Создать» для добавления."
        paginated
        pageSize={20}
        defaultSortKey="name"
        defaultSortDirection="asc"
        onRowClick={handleRowClick}
      />
    </AdminPage>
  );
}

export default PoliciesPage;
