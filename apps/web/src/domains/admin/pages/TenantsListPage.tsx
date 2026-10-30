/**
 * TenantsPage - Управление рабочими группами (EntityPageV2)
 *
 * Единый стиль с остальными админ-реестрами.
 * Клик по строке → View страница, редактирование через кнопку на View.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTenants } from '@shared/hooks/useTenants';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Badge, Button, Input, LifecycleStatusBadge } from '@/shared/ui';
import { ADMIN_ACTION_LABELS, ADMIN_ENTITY_LABELS } from '@/shared/constants/adminLabels';
import type { Tenant } from '@shared/api/tenant';

export function TenantsListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  const {
    tenants,
    loading: isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useTenants(true, debouncedQ);

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
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontWeight: 500 }}>{tenant.name}</span>
          {tenant.is_default && <Badge tone="info">Default</Badge>}
        </div>
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
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <Badge tone={tenant.is_active ? 'success' : 'neutral'}>
            {tenant.is_active ? 'Активен' : 'Неактивен'}
          </Badge>
          {tenant.lifecycle_status === 'deprecated' && (
            <LifecycleStatusBadge
              lifecycleStatus={tenant.lifecycle_status}
              deprecatedAt={tenant.deprecated_at}
              retentionDays={tenant.retention_days}
            />
          )}
        </div>
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
      title="Рабочие группы"
      mode="view"
      breadcrumbs={[{ label: 'Рабочие группы' }]}
      headerActions={
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Input
            placeholder="Поиск рабочих групп..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/tenants/new')}>
          {`${ADMIN_ACTION_LABELS.create} ${ADMIN_ENTITY_LABELS.tenant}`}
        </Button>
      }
    >
      <Tab
        title="Рабочие группы"
        layout="full"
      >
        {error && (
          <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
            Не удалось загрузить рабочие группы. Попробуйте снова.
          </div>
        )}

        <DataTable
          columns={columns}
          data={tenants}
          keyField="id"
          loading={isLoading}
          emptyText={`Рабочие группы не найдены. Нажмите «${ADMIN_ACTION_LABELS.create} ${ADMIN_ENTITY_LABELS.tenant}» для добавления.`}
          paginated
          pageSize={20}
          onRowClick={handleRowClick}
        />
        {hasNextPage && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 16 }}>
            <Button variant="outline" disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}>
              {isFetchingNextPage ? 'Загрузка…' : 'Загрузить ещё'}
            </Button>
          </div>
        )}
      </Tab>
    </EntityPageV2>
  );
}

export default TenantsListPage;
