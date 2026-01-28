/**
 * TenantsPage - Управление тенантами
 * 
 * Единый стиль с остальными админ-реестрами.
 * Клик по строке → View страница, редактирование через кнопку на View.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTenants } from '@shared/hooks/useTenants';
import { AdminPage } from '@shared/ui';
import Badge from '@shared/ui/Badge';
import { AdminTable, type AdminTableColumn } from '@shared/ui/AdminTable';
import type { Tenant } from '@shared/api/admin';

export function TenantsPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  const { tenants, loading: isLoading, error } = useTenants();

  const filteredTenants = useMemo(() => {
    if (!debouncedQ.trim()) return tenants;
    const query = debouncedQ.toLowerCase();
    return tenants.filter((tenant: Tenant) => {
      const name = tenant.name?.toLowerCase() ?? '';
      const desc = tenant.description?.toLowerCase() ?? '';
      return name.includes(query) || desc.includes(query);
    });
  }, [tenants, debouncedQ]);

  const handleRowClick = (tenant: Tenant) => {
    navigate(`/admin/tenants/${tenant.id}`);
  };

  const columns: AdminTableColumn<Tenant>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      sortable: true,
      render: (tenant) => (
        <span style={{ fontWeight: 500 }}>{tenant.name}</span>
      ),
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      render: (tenant) => tenant.description ? (
        <span style={{ color: 'var(--muted)' }}>{tenant.description}</span>
      ) : (
        <span style={{ color: 'var(--muted)' }}>—</span>
      ),
    },
    {
      key: 'is_active',
      label: 'СТАТУС',
      width: 100,
      sortable: true,
      render: (tenant) => (
        <Badge tone={tenant.is_active ? 'success' : 'neutral'} size="small">
          {tenant.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      label: 'СОЗДАН',
      width: 120,
      sortable: true,
      render: (tenant) => (
        <span style={{ color: 'var(--muted)' }}>
          {new Date(tenant.created_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
  ];

  return (
    <AdminPage
      title="Тенанты"
      subtitle="Управление организациями и их настройками"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск тенантов..."
      actions={[
        {
          label: 'Создать',
          onClick: () => navigate('/admin/tenants/new'),
          variant: 'primary',
        },
      ]}
    >
      {error && (
        <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
          Не удалось загрузить тенанты. Попробуйте снова.
        </div>
      )}

      <AdminTable
        columns={columns}
        data={filteredTenants}
        keyField="id"
        loading={isLoading}
        emptyText="Тенанты не найдены. Нажмите «Создать» для добавления."
        paginated
        pageSize={20}
        defaultSortKey="name"
        defaultSortDirection="asc"
        onRowClick={handleRowClick}
      />
    </AdminPage>
  );
}

export default TenantsPage;
