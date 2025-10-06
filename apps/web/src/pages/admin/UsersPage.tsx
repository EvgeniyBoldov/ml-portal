import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  adminApi,
  type User,
  type UserListResponse,
} from '@shared/api/admin';
import { tenantApi, type Tenant } from '@shared/api/tenant';
import { RoleBadge, StatusBadge } from '@shared/ui/RoleBadge';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { FilterIcon, MoreVerticalIcon } from '@shared/ui/Icon';
import Popover from '@shared/ui/Popover';
import styles from './UsersPage.module.css';

export function UsersPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // State
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | undefined>();
  const [, setCurrentCursor] = useState<string | undefined>();

  // Tenants
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(true);

  // Filters (like in RAG)
  const [q, setQ] = useState('');
  const [filters, setFilters] = useState<Partial<Record<string, string>>>({});
  const [pop, setPop] = useState<{
    open: boolean;
    col?: string;
    anchor?: { x: number; y: number };
  }>({ open: false });

  // Load tenants
  const loadTenants = useCallback(async () => {
    try {
      setTenantsLoading(true);
      const response = await tenantApi.getTenants({ size: 100 });
      setTenants(response.tenants);
    } catch (error) {
      console.error('Failed to load tenants:', error);
      showError('Failed to load tenants. Please try again.');
    } finally {
      setTenantsLoading(false);
    }
  }, [showError]);

  // Load users
  const loadUsers = useCallback(
    async (cursor?: string, reset = false) => {
      try {
        setLoading(true);

        const params = {
          query: q || undefined,
          role: filters.role || undefined,
          is_active: filters.status ? filters.status === 'active' : undefined,
          limit: 20,
          cursor,
        };

        const response: UserListResponse = await adminApi.getUsers(params);

        if (reset) {
          setUsers(response.users);
          setCurrentCursor(undefined);
        } else {
          setUsers(prev => [...prev, ...response.users]);
        }

        setTotal(response.total || 0);
        setHasMore(response.has_more);
        setNextCursor(response.next_cursor);
      } catch (error) {
        console.error('Failed to load users:', error);
        showError('Failed to load users. Please try again.');
      } finally {
        setLoading(false);
      }
    },
    [q, filters, showError]
  );

  // Load more users
  const loadMore = useCallback(() => {
    if (hasMore && nextCursor && !loading) {
      setCurrentCursor(nextCursor);
      loadUsers(nextCursor, false);
    }
  }, [hasMore, nextCursor, loading, loadUsers]);

  // Refresh users
  const refreshUsers = useCallback(() => {
    loadUsers(undefined, true);
  }, [loadUsers]);

  // Handle search
  const handleSearch = useCallback(() => {
    loadUsers(undefined, true);
  }, [loadUsers]);

  // Handle sort
  const handleSort = useCallback(
    (column: string, order: 'asc' | 'desc') => {
      setSortBy(column);
      setSortOrder(order);
      loadUsers(undefined, true);
    },
    [loadUsers]
  );

  // Get tenant name by ID
  const getTenantName = useCallback((tenantId: string) => {
    const tenant = tenants.find(t => t.id === tenantId);
    return tenant ? tenant.name : tenantId.substring(0, 8) + '...';
  }, [tenants]);

  // Filter users like in RAG
  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      const text = (
        (user.login || '') +
        ' ' +
        (user.email || '') +
        ' ' +
        (user.role || '') +
        ' ' +
        (user.created_at || '')
      ).toLowerCase();
      
      if (q.trim() && !text.includes(q.toLowerCase())) return false;
      if (filters.role && user.role !== filters.role) return false;
      if (filters.status && user.is_active.toString() !== filters.status) return false;
      
      return true;
    });
  }, [users, q, filters]);

  // Filter functions like in RAG
  function openFilter(col: string, el: HTMLElement) {
    const r = el.getBoundingClientRect();
    setPop({ open: true, col, anchor: { x: r.left, y: r.bottom + 6 } });
  }

  function clearAll() {
    setFilters({});
    setPop({ open: false });
  }

  // Handle user actions
  const handleToggleUserStatus = useCallback(
    async (user: User) => {
      try {
        await adminApi.updateUser(user.id, { is_active: !user.is_active });
        showSuccess(
          `User ${user.login} ${user.is_active ? 'deactivated' : 'activated'} successfully`
        );
        refreshUsers();
      } catch (error) {
        console.error('Failed to toggle user status:', error);
        showError('Failed to update user status. Please try again.');
      }
    },
    [showSuccess, showError, refreshUsers]
  );

  const handleResetPassword = useCallback(
    async (user: User) => {
      const newPassword = window.prompt(`Enter new password for user ${user.login}:`);
      if (!newPassword) return;
      
      try {
        await adminApi.updateUser(user.id, { password: newPassword });
        showSuccess(`Password for user ${user.login} updated successfully`);
        refreshUsers();
      } catch (error) {
        console.error('Failed to reset password:', error);
        showError('Failed to reset password. Please try again.');
      }
    },
    [showSuccess, showError, refreshUsers]
  );

  const handleDeleteUser = useCallback(
    async (user: User) => {
      if (
        !window.confirm(
          `Are you sure you want to deactivate user ${user.login}?`
        )
      ) {
        return;
      }

      try {
        await adminApi.deleteUser(user.id);
        showSuccess(`User ${user.login} deactivated successfully`);
        refreshUsers();
      } catch (error) {
        console.error('Failed to delete user:', error);
        showError('Failed to deactivate user. Please try again.');
      }
    },
    [showSuccess, showError, refreshUsers]
  );

  // Load tenants and users on mount
  useEffect(() => {
    loadTenants();
    loadUsers(undefined, true);
  }, [loadTenants, loadUsers]);

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
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td><Skeleton width={100} /></td>
                    <td><Skeleton width={80} /></td>
                    <td><Skeleton width={120} /></td>
                    <td><Skeleton width={100} /></td>
                    <td><Skeleton width={60} /></td>
                    <td><Skeleton width={80} /></td>
                    <td><Skeleton width={100} /></td>
                  </tr>
                ))
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={7} className={styles.emptyState}>
                    No users found
                  </td>
                </tr>
              ) : (
                filteredUsers.map(user => (
                  <tr key={user.id}>
                    <td>
                      <span className={styles.loginText}>
                        {user.login}
                      </span>
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
                      <div className={styles.actions}>
                        <button
                          className={styles.icon}
                          onClick={() => handleResetPassword(user)}
                          title="Reset Password"
                        >
                          🔑
                        </button>
                        <button
                          className={styles.icon}
                          onClick={() => handleToggleUserStatus(user)}
                          title={user.is_active ? 'Deactivate' : 'Activate'}
                        >
                          {user.is_active ? '⏸️' : '▶️'}
                        </button>
                        <button
                          className={styles.icon}
                          onClick={() => handleDeleteUser(user)}
                          title="Delete"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Popover
          open={pop.open}
          onOpenChange={setPop}
          content={
            <div className={styles.filterPopover}>
              {pop.col === 'role' && (
                <div className={styles.filterGroup}>
                  <label className={styles.filterLabel}>Role</label>
                  <Select
                    value={filters.role || ''}
                    onChange={e => setFilters(prev => ({ ...prev, role: e.target.value }))}
                  >
                    <option value="">All Roles</option>
                    <option value="admin">Admin</option>
                    <option value="editor">Editor</option>
                    <option value="reader">Reader</option>
                  </Select>
                </div>
              )}
              {pop.col === 'status' && (
                <div className={styles.filterGroup}>
                  <label className={styles.filterLabel}>Status</label>
                  <Select
                    value={filters.status || ''}
                    onChange={e => setFilters(prev => ({ ...prev, status: e.target.value }))}
                  >
                    <option value="">All Status</option>
                    <option value="true">Active</option>
                    <option value="false">Inactive</option>
                  </Select>
                </div>
              )}
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
