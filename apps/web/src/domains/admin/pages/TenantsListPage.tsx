/**
 * TenantsPage - Управление тенантами (EntityPageV2)
 * 
 * Единый стиль с остальными админ-реестрами.
 * Клик по строке → View страница, редактирование через кнопку на View.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTenants } from '@shared/hooks/useTenants';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Badge, Button, Input } from '@/shared/ui';
import type { Tenant } from '@shared/api/admin';

export function TenantsListPage() {
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

  const columns: DataTableColumn<Tenant>[] = [
    {
      key: 'name',
      label: 'НАЗВАНИЕ',
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Название',
        getValue: (tenant) => tenant.name,
      },
      render: (tenant) => (
        <span style={{ fontWeight: 500 }}>{tenant.name}</span>
      ),
    },
    {
      key: 'description',
      label: 'ОПИСАНИЕ',
      filter: {
        kind: 'text',
        placeholder: 'Описание',
        getValue: (tenant) => tenant.description ?? '',
      },
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
      filter: {
        kind: 'select',
        placeholder: 'Все статусы',
        options: [
          { value: 'true', label: 'Активен' },
          { value: 'false', label: 'Неактивен' },
        ],
        getValue: (tenant) => String(tenant.is_active),
      },
      render: (tenant) => (
        <Badge tone={tenant.is_active ? 'success' : 'neutral'}>
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
    <EntityPageV2
      title="Тенанты"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск тенантов..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/tenants/new')}>
          Создать
        </Button>
      }
    >
      <Tab 
        title="Тенанты" 
        layout="full"
      >
        {error && (
          <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
            Не удалось загрузить тенанты. Попробуйте снова.
          </div>
        )}

        <DataTable
          columns={columns}
          data={filteredTenants}
          keyField="id"
          loading={isLoading}
          emptyText="Тенанты не найдены. Нажмите «Создать» для добавления."
          paginated
          pageSize={20}
          onRowClick={handleRowClick}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default TenantsListPage;
