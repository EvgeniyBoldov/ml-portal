/**
 * TenantsPage - Управление тенантами
 */
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { ActionsButton, type ActionItem } from '@shared/ui/ActionsButton';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import { tenantApi } from '@shared/api/tenant';
import type { Tenant } from '@shared/api/admin';
import styles from './RegistryPage.module.css';

export function TenantsPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const [q, setQ] = useState('');

  const { tenants, loading: isLoading, error, refetch } = useTenants();

  const filteredTenants = React.useMemo(() => {
    if (!q.trim()) return tenants;
    const query = q.toLowerCase();
    return tenants.filter((tenant: Tenant) => {
      const name = tenant.name?.toLowerCase() ?? '';
      const id = tenant.id?.toLowerCase() ?? '';
      return name.includes(query) || id.includes(query);
    });
  }, [tenants, q]);

  const getActions = (tenant: Tenant): ActionItem[] => [
    {
      label: 'Редактировать',
      onClick: () => navigate(`/admin/tenants/${tenant.id}/edit`),
    },
    {
      label: 'Просмотр',
      onClick: () => navigate(`/admin/tenants/${tenant.id}`),
    },
    {
      label: 'Удалить',
      variant: 'danger',
      onClick: () =>
        showConfirmDialog({
          title: `Удалить тенант «${tenant.name || tenant.id}»?`,
          confirmLabel: 'Удалить',
          cancelLabel: 'Отмена',
          variant: 'danger',
          message: (
            <Alert
              variant="danger"
              title="Действие необратимо"
              description={
                <>
                  Тенант будет удалён окончательно. Перед удалением убедитесь,
                  что в нём не осталось пользователей — иначе бэкенд politely
                  ответит отказом.
                </>
              }
            />
          ),
          onConfirm: async () => {
            try {
              await tenantApi.deleteTenant(tenant.id);
              showSuccess('Тенант удалён');
              await refetch?.();
            } catch (err) {
              const message =
                err instanceof Error
                  ? err.message
                  : 'Не удалось удалить тенант';
              showError(message);
            }
          },
        }),
    },
  ];

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.errorState}>Не удалось загрузить тенанты</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Тенанты</h1>
            <p className={styles.subtitle}>Управление организациями и их настройками</p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск тенантов..."
              value={q}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setQ(event.target.value)
              }
              className={styles.search}
            />
            <Link to="/admin/tenants/new">
              <Button>Создать</Button>
            </Link>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ИМЯ</th>
                <th>ОПИСАНИЕ</th>
                <th>EMBED МОДЕЛИ</th>
                <th>RERANK МОДЕЛЬ</th>
                <th>СОЗДАН</th>
                <th>ДЕЙСТВИЯ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td>
                      <Skeleton width={200} />
                    </td>
                    <td>
                      <Skeleton width={150} />
                    </td>
                    <td>
                      <Skeleton width={120} />
                    </td>
                    <td>
                      <Skeleton width={120} />
                    </td>
                    <td>
                      <Skeleton width={120} />
                    </td>
                    <td>
                      <Skeleton width={80} />
                    </td>
                  </tr>
                ))
              ) : filteredTenants.length === 0 ? (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    Тенанты не найдены
                  </td>
                </tr>
              ) : (
                filteredTenants.map(tenant => (
                  <tr key={tenant.id}>
                    <td>{tenant.name}</td>
                    <td>
                      {tenant.description ? (
                        <span title={tenant.description}>
                          {tenant.description.length > 50
                            ? `${tenant.description.substring(0, 50)}...`
                            : tenant.description}
                        </span>
                      ) : (
                        <span className={styles.muted}>—</span>
                      )}
                    </td>
                    <td>
                      {tenant.embed_models && tenant.embed_models.length > 0 ? (
                        <div
                          style={{
                            display: 'flex',
                            gap: '4px',
                            flexWrap: 'wrap',
                          }}
                        >
                          {tenant.embed_models.map((model: string) => (
                            <Badge key={model} tone="info" size="small">
                              {model}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className={styles.muted}>—</span>
                      )}
                    </td>
                    <td>
                      {tenant.rerank_model ? (
                        <Badge tone="success" size="small">
                          {tenant.rerank_model}
                        </Badge>
                      ) : (
                        <span className={styles.muted}>—</span>
                      )}
                    </td>
                    <td>{new Date(tenant.created_at).toLocaleDateString()}</td>
                    <td>
                      <ActionsButton actions={getActions(tenant)} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default TenantsPage;
