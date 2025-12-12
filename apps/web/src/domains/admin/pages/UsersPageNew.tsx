/**
 * UsersPage - Admin users management (redesigned)
 */
import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import type { User } from '@shared/api/admin';
import { useUsers, useDeleteUser, useUpdateUser } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Icon } from '@shared/ui/Icon';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import styles from './UsersPageNew.module.css';

const ROLE_CONFIG: Record<string, { label: string; color: string; variant: 'default' | 'success' | 'warning' | 'danger' }> = {
  admin: { label: 'Админ', color: 'var(--color-danger)', variant: 'danger' },
  editor: { label: 'Редактор', color: 'var(--color-warning)', variant: 'warning' },
  reader: { label: 'Читатель', color: 'var(--color-text-muted)', variant: 'default' },
};

export function UsersPageNew() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);

  const [q, setQ] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const { data, isLoading, error } = useUsers({ limit: 100 });
  const deleteUserMutation = useDeleteUser();
  const updateUserMutation = useUpdateUser();
  const { tenants } = useTenants();

  const users = data?.users || [];

  const filteredUsers = useMemo(() => {
    let result = users;

    if (q.trim()) {
      const query = q.toLowerCase();
      result = result.filter(
        (user: User) =>
          user.login.toLowerCase().includes(query) ||
          (user.email?.toLowerCase() || '').includes(query)
      );
    }

    if (roleFilter) {
      result = result.filter((user: User) => user.role === roleFilter);
    }

    if (statusFilter) {
      const isActive = statusFilter === 'active';
      result = result.filter((user: User) => user.is_active === isActive);
    }

    return result;
  }, [users, q, roleFilter, statusFilter]);

  const getTenantName = (tenantId: string | undefined) => {
    if (!tenantId || !tenants) return null;
    const tenant = tenants.find((t: any) => t.id === tenantId);
    return tenant?.name || null;
  };

  const handleToggleStatus = async (user: User) => {
    try {
      await updateUserMutation.mutateAsync({
        id: user.id,
        data: { is_active: !user.is_active },
      });
      showSuccess(`Пользователь ${user.is_active ? 'деактивирован' : 'активирован'}`);
    } catch {
      showError('Ошибка обновления статуса');
    }
  };

  const handleDelete = async (user: User) => {
    showConfirmDialog({
      title: `Удалить пользователя «${user.login}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Действие необратимо"
          description="Пользователь будет удалён. Все его сессии будут завершены."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteUserMutation.mutateAsync(user.id);
          showSuccess('Пользователь удалён');
        } catch {
          showError('Ошибка удаления');
        }
      },
    });
  };

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.error}>
          <Icon name="alert-triangle" size={24} />
          <span>Не удалось загрузить пользователей</span>
        </div>
      </div>
    );
  }

  const activeFilters = [roleFilter, statusFilter].filter(Boolean).length;

  return (
    <div className={styles.wrap}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleSection}>
          <h1 className={styles.title}>Пользователи</h1>
          <span className={styles.count}>{filteredUsers.length} из {users.length}</span>
        </div>
        <div className={styles.actions}>
          <div className={styles.searchWrap}>
            <Icon name="search" size={18} className={styles.searchIcon} />
            <Input
              placeholder="Поиск по логину или email..."
              value={q}
              onChange={e => setQ(e.target.value)}
              className={styles.search}
            />
          </div>
          <Button onClick={() => navigate('/admin/users/new')}>
            <Icon name="plus" size={16} />
            Создать
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label>Роль</label>
          <select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value)}
            className={styles.filterSelect}
          >
            <option value="">Все роли</option>
            <option value="admin">Админ</option>
            <option value="editor">Редактор</option>
            <option value="reader">Читатель</option>
          </select>
        </div>
        <div className={styles.filterGroup}>
          <label>Статус</label>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className={styles.filterSelect}
          >
            <option value="">Все статусы</option>
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
          </select>
        </div>
        {activeFilters > 0 && (
          <Button
            variant="ghost"
            size="small"
            onClick={() => {
              setRoleFilter('');
              setStatusFilter('');
            }}
          >
            Сбросить ({activeFilters})
          </Button>
        )}
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Пользователь</th>
              <th>Роль</th>
              <th>Тенант</th>
              <th>Статус</th>
              <th>Создан</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  <td><Skeleton width={180} height={40} /></td>
                  <td><Skeleton width={80} /></td>
                  <td><Skeleton width={100} /></td>
                  <td><Skeleton width={70} /></td>
                  <td><Skeleton width={90} /></td>
                  <td><Skeleton width={40} /></td>
                </tr>
              ))
            ) : filteredUsers.length === 0 ? (
              <tr>
                <td colSpan={6} className={styles.emptyRow}>
                  <div className={styles.empty}>
                    <Icon name="users" size={32} />
                    <p>Пользователи не найдены</p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredUsers.map((user: User) => {
                const roleConfig = ROLE_CONFIG[user.role] || ROLE_CONFIG.reader;
                const tenantName = getTenantName(user.tenant_id);

                return (
                  <tr key={user.id} className={!user.is_active ? styles.inactive : ''}>
                    <td>
                      <div className={styles.userCell}>
                        <div className={styles.avatar}>
                          {user.login.charAt(0).toUpperCase()}
                        </div>
                        <div className={styles.userInfo}>
                          <span className={styles.login}>{user.login}</span>
                          {user.email && (
                            <span className={styles.email}>{user.email}</span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <Badge variant={roleConfig.variant} size="small">
                        {roleConfig.label}
                      </Badge>
                    </td>
                    <td>
                      {tenantName ? (
                        <span className={styles.tenant}>{tenantName}</span>
                      ) : (
                        <span className={styles.muted}>—</span>
                      )}
                    </td>
                    <td>
                      <div className={styles.statusCell}>
                        <span
                          className={`${styles.statusDot} ${user.is_active ? styles.active : ''}`}
                        />
                        <span>{user.is_active ? 'Активен' : 'Неактивен'}</span>
                      </div>
                    </td>
                    <td>
                      <span className={styles.date}>
                        {new Date(user.created_at).toLocaleDateString('ru-RU')}
                      </span>
                    </td>
                    <td>
                      <div className={styles.rowActions}>
                        <button
                          className={styles.actionBtn}
                          onClick={() => navigate(`/admin/users/${user.id}`)}
                          title="Редактировать"
                        >
                          <Icon name="edit" size={16} />
                        </button>
                        <button
                          className={styles.actionBtn}
                          onClick={() => handleToggleStatus(user)}
                          title={user.is_active ? 'Деактивировать' : 'Активировать'}
                        >
                          <Icon name={user.is_active ? 'user-x' : 'user-check'} size={16} />
                        </button>
                        <button
                          className={`${styles.actionBtn} ${styles.danger}`}
                          onClick={() => handleDelete(user)}
                          title="Удалить"
                        >
                          <Icon name="trash" size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default UsersPageNew;
