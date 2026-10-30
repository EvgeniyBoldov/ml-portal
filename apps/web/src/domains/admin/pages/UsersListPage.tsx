/**
 * UsersPage - Управление пользователями (EntityPageV2)
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { User } from '@shared/api/admin';
import { useUsers } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import type { Tenant } from '@shared/api/tenant';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage';
import { DataTable, type DataTableColumn, Badge, Button, Input, LifecycleStatusBadge } from '@/shared/ui';
import { ADMIN_ACTION_LABELS, ADMIN_ENTITY_LABELS } from '@/shared/constants/adminLabels';

export function UsersListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  const queryParams = useMemo(
    () => ({
      query: debouncedQ || undefined,
      limit: 100,
      include_deprecated: true,
    }),
    [debouncedQ]
  );

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } = useUsers(queryParams);
  const { tenants = [] } = useTenants(true);

  const users = data?.pages.flatMap(page => page.users) ?? [];

  const getTenantName = React.useCallback(
    (tenantId: string | null | undefined) => {
      if (!tenantId || !tenants) return null;
      const tenant = tenants.find((t: Tenant) => t.id === tenantId);
      return tenant?.name || null;
    },
    [tenants]
  );

  const handleRowClick = (user: User) => {
    navigate(`/admin/users/${user.id}`);
  };

  const columns: DataTableColumn<User>[] = [
    {
      key: 'login',
      label: 'ИМЯ / ЛОГИН / EMAIL',
      width: 280,
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Логин или email',
        getValue: (user) => `${user.full_name ?? ''} ${user.login ?? ''} ${user.email ?? ''}`,
      },
      render: (user) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{user.full_name || user.login}</span>
          {user.full_name && <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{user.login}</span>}
          {user.email && <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{user.email}</span>}
        </div>
      ),
    },
    {
      key: 'is_admin',
      label: 'ДОСТУП К АДМИНКЕ',
      width: 100,
      sortable: true,
      filter: {
        kind: 'select',
        placeholder: 'Любой доступ',
        options: [
          { value: 'true', label: 'Администратор' },
          { value: 'false', label: 'Пользователь' },
        ],
        getValue: (user) => String(user.is_admin),
      },
      render: (user) => <Badge tone={user.is_admin ? 'danger' : 'neutral'}>{user.is_admin ? 'Администратор' : 'Пользователь'}</Badge>,
    },
    {
      key: 'auth_provider',
      label: 'ТИП',
      width: 100,
      sortable: true,
      render: (user) => (
        <Badge tone={user.auth_provider === 'ldap' ? 'info' : 'neutral'}>
          {user.auth_provider === 'ldap' ? 'LDAP' : 'Локальная'}
        </Badge>
      ),
    },
    {
      key: 'tenant_id',
      label: 'ТЕНАНТ',
      sortable: true,
      filter: {
        kind: 'text',
        placeholder: 'Рабочая группа',
        getValue: (user) => getTenantName(user.tenant_id) ?? '',
      },
      render: (user) => {
        const tenantName = getTenantName(user.tenant_id);
        return tenantName ? (
          <span>{tenantName}</span>
        ) : (
          <span style={{ color: 'var(--muted)' }}>—</span>
        );
      },
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
        getValue: (user) => String(user.is_active),
      },
      render: (user) => (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <Badge tone={user.is_active ? 'success' : 'neutral'}>
            {user.is_active ? 'Активен' : 'Неактивен'}
          </Badge>
          {user.lifecycle_status === 'deprecated' && (
            <LifecycleStatusBadge
              lifecycleStatus={user.lifecycle_status}
              deprecatedAt={user.deprecated_at}
              retentionDays={user.retention_days}
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
      render: (user) => (
        <span style={{ color: 'var(--muted)' }}>
          {new Date(user.created_at).toLocaleDateString('ru-RU')}
        </span>
      ),
    },
    {
      key: 'last_login_at',
      label: 'ПОСЛЕДНИЙ ВХОД',
      width: 150,
      render: (user) => (
        <span style={{ color: 'var(--muted)' }}>
          {user.last_login_at ? new Date(user.last_login_at).toLocaleString('ru-RU') : '—'}
        </span>
      ),
    },
  ];

  return (
    <EntityPageV2
      title="Пользователи"
      mode="view"
      breadcrumbs={[{ label: 'Пользователи' }]}
      headerActions={
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Input
            placeholder="Поиск пользователей..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/users/new')}>
          {`${ADMIN_ACTION_LABELS.create} ${ADMIN_ENTITY_LABELS.user}`}
        </Button>
      }
    >
      <Tab 
        title="Пользователи" 
        layout="full"
      >
        {error && (
          <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
            Не удалось загрузить пользователей. Попробуйте снова.
          </div>
        )}

        <DataTable
          columns={columns}
          data={users}
          keyField="id"
          loading={isLoading}
          emptyText={`Пользователи не найдены. Нажмите «${ADMIN_ACTION_LABELS.create} ${ADMIN_ENTITY_LABELS.user}» для добавления.`}
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

export default UsersListPage;
