import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  adminApi,
  type User,
  type UserListResponse,
} from '@shared/api/admin';
import { Table, type TableColumn } from '@shared/ui/Table';
import { RoleBadge, StatusBadge } from '@shared/ui/RoleBadge';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
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

  // Filters
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Load users
  const loadUsers = useCallback(
    async (cursor?: string, reset = false) => {
      try {
        setLoading(true);

        const params = {
          query: query || undefined,
          role: roleFilter || undefined,
          is_active: statusFilter ? statusFilter === 'active' : undefined,
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
    [query, roleFilter, statusFilter, showError]
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

  // Load users on mount and when filters change
  useEffect(() => {
    loadUsers(undefined, true);
  }, [loadUsers]);

  // Table columns
  const columns: TableColumn<User>[] = [
    {
      key: 'login',
      title: 'Login',
      dataIndex: 'login',
      sortable: true,
      render: (value, record) => (
        <Link
          to={`/admin/users/${record.id}`}
          className="text-primary hover:text-primary-dark font-medium"
        >
          {value}
        </Link>
      ),
    },
    {
      key: 'role',
      title: 'Role',
      dataIndex: 'role',
      sortable: true,
      render: value => <RoleBadge role={value as any} />,
    },
    {
      key: 'email',
      title: 'Email',
      dataIndex: 'email',
      render: value => value || <span className="text-text-tertiary">—</span>,
    },
    {
      key: 'is_active',
      title: 'Status',
      dataIndex: 'is_active',
      sortable: true,
      render: value => <StatusBadge active={value} />,
    },
    {
      key: 'created_at',
      title: 'Created',
      dataIndex: 'created_at',
      sortable: true,
      render: value => new Date(value).toLocaleDateString(),
    },
    {
      key: 'actions',
      title: 'Actions',
      render: (_, record) => (
        <div className="flex gap-2">
          <Button
            size="small"
            variant="outline"
            onClick={() => navigate(`/admin/users/${record.id}`)}
          >
            View
          </Button>
          <Button
            size="small"
            variant="outline"
            onClick={() => handleToggleUserStatus(record)}
          >
            {record.is_active ? 'Deactivate' : 'Activate'}
          </Button>
          <Button
            size="small"
            variant="danger"
            onClick={() => handleDeleteUser(record)}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Users</h1>
        <div className={styles.pageActions}>
          <Button onClick={refreshUsers} variant="outline">
            Refresh
          </Button>
          <Button onClick={() => navigate('/admin/users/new')}>
            Create User
          </Button>
        </div>
      </div>

      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Search</label>
          <Input
            placeholder="Search by login or email..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSearch()}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Role</label>
          <Select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value)}
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
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </Select>
        </div>

        <div className={styles.filterActions}>
          <Button onClick={handleSearch} variant="outline">
            Search
          </Button>
          <Button
            onClick={() => {
              setQuery('');
              setRoleFilter('');
              setStatusFilter('');
              loadUsers(undefined, true);
            }}
            variant="outline"
          >
            Clear
          </Button>
        </div>
      </div>

      <div className={styles.tableContainer}>
        <div className={styles.tableHeader}>
          <h2 className={styles.tableTitle}>Users List</h2>
          <div className={styles.tableStats}>
            {loading ? (
              <Skeleton width={100} />
            ) : (
              `Showing ${users.length} of ${total} users`
            )}
          </div>
        </div>

        <div className={styles.tableContent}>
          {loading && users.length === 0 ? (
            <div className={styles.loadingState}>
              <div className={styles.loadingSpinner} />
              <p>Loading users...</p>
            </div>
          ) : (
            <Table
              columns={columns}
              data={users}
              loading={loading}
              onSort={handleSort}
              sortBy={sortBy}
              sortOrder={sortOrder}
              emptyText="No users found"
              emptyIcon="👥"
            />
          )}
        </div>

        {hasMore && (
          <div className={styles.pagination}>
            <div className={styles.paginationInfo}>
              Showing {users.length} of {total} users
            </div>
            <div className={styles.paginationControls}>
              <Button onClick={loadMore} disabled={loading} variant="outline">
                {loading ? 'Loading...' : 'Load More'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default UsersPage;
