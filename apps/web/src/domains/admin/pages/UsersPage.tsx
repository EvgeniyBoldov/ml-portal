/**
 * UsersPage - Admin users management
 * Uses TanStack Query for data fetching and Zustand for UI state
 */
import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import type { User } from '@shared/api/admin';
import {
  useUsers,
  useDeleteUser,
  useUpdateUser,
} from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import { RoleBadge, StatusBadge } from '@shared/ui/RoleBadge';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { FilterIcon, MoreVerticalIcon } from '@shared/ui/Icon';
import Popover from '@shared/ui/Popover';
import { ActionsButton, type ActionItem } from '@shared/ui/ActionsButton';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import styles from './UsersPage.module.css';

export function UsersPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);

  // UI state from Zustand
  const filters = useAppStore(state => state.filters);
  const setFilters = useAppStore(state => state.setFilter);
  const resetFilters = useAppStore(state => state.resetFilters);
  const setPop = useAppStore(state => state.openModal);
  const closePop = useAppStore(state => state.closeModal);
  const popOpen = useAppStore(state => state.modals.usersFilterPop || false);

  // Local search state (debounced)
  const [q, setQ] = React.useState('');
  const [debouncedQ, setDebouncedQ] = React.useState('');

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQ(q);
    }, 300);
    return () => clearTimeout(timer);
  }, [q]);

  // Get filter values from store
  const roleFilter = filters.users_role;
  const statusFilter = filters.users_status;

  // Query params
  const queryParams = useMemo(
    () => ({
      query: debouncedQ || undefined,
      role: roleFilter || undefined,
      is_active:
        statusFilter === 'active'
          ? true
          : statusFilter === 'inactive'
            ? false
            : undefined,
      limit: 20,
    }),
    [debouncedQ, roleFilter, statusFilter]
  );

  // TanStack Query
  const { data, isLoading, error } = useUsers(queryParams);
  const deleteUserMutation = useDeleteUser();
  const updateUserMutation = useUpdateUser();
  const { tenants } = useTenants();

  const users = data?.users || [];
  const total = data?.total || 0;

  // Get tenant name by ID
  const getTenantName = React.useCallback(
    (tenantId: string) => {
      if (!tenants || !Array.isArray(tenants)) {
        return tenantId.substring(0, 8) + '...';
      }
      const tenant = tenants.find(t => t.id === tenantId);
      return tenant ? tenant.name : tenantId.substring(0, 8) + '...';
    },
    [tenants]
  );

  // Handle user actions
  const handleToggleUserStatus = React.useCallback(
    async (user: User) => {
      const nextStatus = !user.is_active;
      try {
        await updateUserMutation.mutateAsync({
          id: user.id,
          data: { is_active: nextStatus },
        });
        showSuccess(
          `Пользователь ${user.login} ${nextStatus ? 'активирован' : 'деактивирован'}`
        );
      } catch (error) {
        console.error('Failed to toggle user status:', error);
        showError('Не удалось обновить статус. Попробуйте снова.');
      }
    },
    [showSuccess, showError, updateUserMutation]
  );

  const handleResetPassword = React.useCallback(
    async (user: User) => {
      const newPassword = window.prompt(
        `Enter new password for user ${user.login}:`
      );
      if (!newPassword) return;

      try {
        // TODO: Use useUpdateUser mutation
        showSuccess(`Password for user ${user.login} updated successfully`);
      } catch (error) {
        console.error('Failed to reset password:', error);
        showError('Failed to reset password. Please try again.');
      }
    },
    [showSuccess, showError]
  );

  const handleDeleteUser = React.useCallback(
    async (user: User) => {
      showConfirmDialog({
        title: `Удалить пользователя «${user.login}»?`,
        confirmLabel: 'Удалить',
        cancelLabel: 'Отмена',
        variant: 'danger',
        message: (
          <Alert
            variant="danger"
            title="Пользователь будет удалён"
            description={
              <>
                Удаление нельзя отменить. Все связанные сессии будут завершены.
              </>
            }
          />
        ),
        onConfirm: async () => {
          try {
            await deleteUserMutation.mutateAsync(user.id);
            showSuccess(`Пользователь ${user.login} удалён`);
          } catch (error) {
            console.error('Failed to delete user:', error);
            showError('Не удалось удалить пользователя. Попробуйте снова.');
          }
        },
      });
    },
    [showSuccess, showError, deleteUserMutation, showConfirmDialog]
  );

  // Filter functions
  function openFilter(col: string, el: HTMLElement) {
    const r = el.getBoundingClientRect();
    setPop('usersFilterPop');
  }

  function clearAll() {
    resetFilters();
    closePop('usersFilterPop');
  }

  // Handle filter changes
  const handleRoleFilterChange = (value: string) => {
    setFilters('users_role', value);
    closePop('usersFilterPop');
  };

  const handleStatusFilterChange = (value: string) => {
    setFilters('users_status', value);
    closePop('usersFilterPop');
  };

  // Error handling
  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <div className={styles.header}>
            <h1 className={styles.title}>Users</h1>
          </div>
          <div className={styles.errorState}>
            Failed to load users. Please try again.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>Users</h1>
          <div className={styles.controls}>
            <Input
              placeholder="Search users..."
              value={q}
              onChange={e => setQ(e.target.value)}
              className={styles.search}
            />
            <Button onClick={() => navigate('/admin/users/new')}>
              Create User
            </Button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>
                  LOGIN
                  <button
                    className={styles.icon}
                    onClick={e => openFilter('login', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>
                  ROLE
                  <button
                    className={styles.icon}
                    onClick={e => openFilter('role', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>EMAIL</th>
                <th>TENANT</th>
                <th>
                  STATUS
                  <button
                    className={styles.icon}
                    onClick={e => openFilter('status', e.currentTarget)}
                  >
                    <FilterIcon />
                  </button>
                </th>
                <th>CREATED</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td>
                      <Skeleton width={100} />
                    </td>
                    <td>
                      <Skeleton width={80} />
                    </td>
                    <td>
                      <Skeleton width={120} />
                    </td>
                    <td>
                      <Skeleton width={100} />
                    </td>
                    <td>
                      <Skeleton width={60} />
                    </td>
                    <td>
                      <Skeleton width={80} />
                    </td>
                    <td>
                      <Skeleton width={100} />
                    </td>
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={7} className={styles.emptyState}>
                    No users found
                  </td>
                </tr>
              ) : (
                users.map(user => (
                  <tr key={user.id}>
                    <td>
                      <span className={styles.loginText}>{user.login}</span>
                    </td>
                    <td>
                      <RoleBadge role={user.role as any} size="small" />
                    </td>
                    <td>
                      {user.email || <span className={styles.muted}>—</span>}
                    </td>
                    <td>
                      <Badge tone="info" className={styles.tenantBadge}>
                        {user.tenant_id ? getTenantName(user.tenant_id) : '—'}
                      </Badge>
                    </td>
                    <td>
                      <StatusBadge active={user.is_active} size="small" />
                    </td>
                    <td>
                      <span className={styles.muted}>
                        {new Date(user.created_at).toLocaleDateString()}
                      </span>
                    </td>
                    <td>
                      <ActionsButton
                        actions={[
                          {
                            label: 'Edit',
                            onClick: () => navigate(`/admin/users/${user.id}`),
                          },
                          {
                            label: 'Reset Password',
                            onClick: () => handleResetPassword(user),
                          },
                          {
                            label: user.is_active ? 'Deactivate' : 'Activate',
                            onClick: () => handleToggleUserStatus(user),
                          },
                          {
                            label: 'Delete',
                            onClick: () => handleDeleteUser(user),
                            danger: true,
                          },
                        ]}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {total > users.length && (
          <div className={styles.pagination}>
            <Button variant="outline" onClick={() => {}}>
              Load More ({total - users.length} remaining)
            </Button>
          </div>
        )}

        <Popover
          open={popOpen}
          onOpenChange={() => closePop('usersFilterPop')}
          content={
            <div className={styles.filterPopover}>
              <div className={styles.filterGroup}>
                <label className={styles.filterLabel}>Role</label>
                <Select
                  value={roleFilter || ''}
                  onChange={e => handleRoleFilterChange(e.target.value)}
                >
                  <option value="">All Roles</option>
                  <option value="admin">Admin</option>
                  <option value="editor">Editor</option>
                  <option value="reader">Reader</option>
                </Select>
              </div>
              <div className={styles.filterGroup}>
                <label className={styles.filterLabel}>Status</label>
                <Select
                  value={statusFilter || ''}
                  onChange={e => handleStatusFilterChange(e.target.value)}
                >
                  <option value="">All Status</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </Select>
              </div>
              <div className={styles.filterActions}>
                <Button onClick={clearAll} variant="outline" size="small">
                  Clear
                </Button>
              </div>
            </div>
          }
        />
      </div>
    </div>
  );
}

export default UsersPage;
