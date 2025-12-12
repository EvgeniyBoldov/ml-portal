/**
 * TenantsPage - Admin tenants management (redesigned)
 */
import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Icon } from '@shared/ui/Icon';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import { tenantApi } from '@shared/api/tenant';
import type { Tenant } from '@shared/api/admin';
import styles from './TenantsPageNew.module.css';

export function TenantsPageNew() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const [q, setQ] = useState('');

  const { tenants, loading: isLoading, error, refetch } = useTenants();

  const filteredTenants = useMemo(() => {
    if (!q.trim()) return tenants;
    const query = q.toLowerCase();
    return tenants.filter((tenant: Tenant) => {
      const name = tenant.name?.toLowerCase() ?? '';
      const desc = tenant.description?.toLowerCase() ?? '';
      return name.includes(query) || desc.includes(query);
    });
  }, [tenants, q]);

  const handleDelete = async (tenant: Tenant) => {
    showConfirmDialog({
      title: `Удалить тенант «${tenant.name}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Действие необратимо"
          description="Тенант будет удалён. Убедитесь, что в нём нет пользователей."
        />
      ),
      onConfirm: async () => {
        try {
          await tenantApi.deleteTenant(tenant.id);
          showSuccess('Тенант удалён');
          await refetch?.();
        } catch (err) {
          showError(err instanceof Error ? err.message : 'Ошибка удаления');
        }
      },
    });
  };

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.error}>
          <Icon name="alert-triangle" size={24} />
          <span>Не удалось загрузить тенанты</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleSection}>
          <h1 className={styles.title}>Тенанты</h1>
          <span className={styles.count}>{tenants.length} всего</span>
        </div>
        <div className={styles.actions}>
          <div className={styles.searchWrap}>
            <Icon name="search" size={18} className={styles.searchIcon} />
            <Input
              placeholder="Поиск..."
              value={q}
              onChange={e => setQ(e.target.value)}
              className={styles.search}
            />
          </div>
          <Button onClick={() => navigate('/admin/tenants/new')}>
            <Icon name="plus" size={16} />
            Создать
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Название</th>
              <th>Описание</th>
              <th>Статус</th>
              <th>Создан</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i}>
                  <td><Skeleton width={150} /></td>
                  <td><Skeleton width={200} /></td>
                  <td><Skeleton width={80} /></td>
                  <td><Skeleton width={100} /></td>
                  <td><Skeleton width={40} /></td>
                </tr>
              ))
            ) : filteredTenants.length === 0 ? (
              <tr>
                <td colSpan={5} className={styles.emptyRow}>
                  <div className={styles.empty}>
                    <Icon name="building" size={32} />
                    <p>Тенанты не найдены</p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredTenants.map((tenant: Tenant) => (
                <tr key={tenant.id}>
                  <td>
                    <div className={styles.tenantCell}>
                      <div className={styles.tenantIcon}>
                        <Icon name="building" size={16} />
                      </div>
                      <span className={styles.tenantName}>{tenant.name}</span>
                    </div>
                  </td>
                  <td>
                    <span className={styles.description}>
                      {tenant.description || <span className={styles.muted}>—</span>}
                    </span>
                  </td>
                  <td>
                    <Badge variant={tenant.is_active ? 'success' : 'default'} size="small">
                      {tenant.is_active ? 'Активен' : 'Неактивен'}
                    </Badge>
                  </td>
                  <td>
                    <span className={styles.date}>
                      {new Date(tenant.created_at).toLocaleDateString('ru-RU')}
                    </span>
                  </td>
                  <td>
                    <div className={styles.rowActions}>
                      <button
                        className={styles.actionBtn}
                        onClick={() => navigate(`/admin/tenants/${tenant.id}/edit`)}
                        title="Редактировать"
                      >
                        <Icon name="edit" size={16} />
                      </button>
                      <button
                        className={`${styles.actionBtn} ${styles.danger}`}
                        onClick={() => handleDelete(tenant)}
                        title="Удалить"
                      >
                        <Icon name="trash" size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default TenantsPageNew;
