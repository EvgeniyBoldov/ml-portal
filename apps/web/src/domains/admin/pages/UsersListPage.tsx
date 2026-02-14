/**
 * UsersPage - Управление пользователями (EntityPageV2)
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { User } from '@shared/api/admin';
import { useUsers } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';
import { DataTable, type DataTableColumn, Badge, Button, Input } from '@/shared/ui';

const ROLE_CONFIG: Record<string, { label: string; tone: 'danger' | 'warn' | 'info' | 'neutral' }> = {
  admin: { label: 'Админ', tone: 'danger' },
  editor: { label: 'Редактор', tone: 'warn' },
  reader: { label: 'Читатель', tone: 'neutral' },
};

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
    }),
    [debouncedQ]
  );

  const { data, isLoading, error } = useUsers(queryParams);
  const { tenants } = useTenants();

  const users = data?.users || [];

  const getTenantName = React.useCallback(
    (tenantId: string | undefined) => {
      if (!tenantId || !tenants) return null;
      const tenant = tenants.find((t: any) => t.id === tenantId);
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
      label: 'ЛОГИН / EMAIL',
      width: 280,
      sortable: true,
      render: (user) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{user.login}</span>
          {user.email && <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{user.email}</span>}
        </div>
      ),
    },
    {
      key: 'role',
      label: 'РОЛЬ',
      width: 100,
      sortable: true,
      render: (user) => {
        const roleConfig = ROLE_CONFIG[user.role] || ROLE_CONFIG.reader;
        return (
          <Badge tone={roleConfig.tone} size="small">
            {roleConfig.label}
          </Badge>
        );
      },
    },
    {
      key: 'tenant_id',
      label: 'ТЕНАНТ',
      sortable: true,
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
      render: (user) => (
        <Badge tone={user.is_active ? 'success' : 'neutral'} size="small">
          {user.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
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
  ];

  return (
    <EntityPageV2
      title="Пользователи"
      mode="view"
      headerActions={
        <Input
          placeholder="Поиск пользователей..."
          value={q}
          onChange={setQ}
        />
      }
      actionButtons={
        <Button onClick={() => navigate('/admin/users/new')}>
          Создать
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
          emptyText="Пользователи не найдены. Нажмите «Создать» для добавления."
          paginated
          pageSize={20}
          onRowClick={handleRowClick}
        />
      </Tab>
    </EntityPageV2>
  );
}

export default UsersListPage;
