/**
 * CollectionsPage - Управление коллекциями
 */
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { ActionsButton, type ActionItem } from '@shared/ui/ActionsButton';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import { collectionsApi, type Collection } from '@shared/api/collections';
import { adminApi } from '@shared/api/admin';
import styles from './RegistryPage.module.css';

export function CollectionsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  const [q, setQ] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin', 'collections'],
    queryFn: () => collectionsApi.listAll({ size: 100 }),
  });

  const { data: tenantsData } = useQuery({
    queryKey: ['admin', 'tenants'],
    queryFn: () => adminApi.getTenants(),
  });

  const tenants = tenantsData?.items ?? [];
  const getTenantName = (tenantId?: string) => {
    if (!tenantId) return '—';
    const tenant = tenants.find(t => t.id === tenantId);
    return tenant?.name || tenantId.slice(0, 8);
  };

  const deleteMutation = useMutation({
    mutationFn: (id: string) => collectionsApi.delete(id, true),
    onSuccess: () => {
      showSuccess('Коллекция удалена');
      queryClient.invalidateQueries({ queryKey: ['admin', 'collections'] });
    },
    onError: (err: Error) => {
      showError(err.message || 'Не удалось удалить коллекцию');
    },
  });

  const collections = data?.items ?? [];

  const filteredCollections = React.useMemo(() => {
    if (!q.trim()) return collections;
    const query = q.toLowerCase();
    return collections.filter((c: Collection) => {
      const name = c.name?.toLowerCase() ?? '';
      const slug = c.slug?.toLowerCase() ?? '';
      return name.includes(query) || slug.includes(query);
    });
  }, [collections, q]);

  const getActions = (collection: Collection): ActionItem[] => [
    {
      label: 'Просмотр',
      onClick: () => navigate(`/admin/collections/${collection.id}`),
    },
    {
      label: 'Удалить',
      variant: 'danger',
      onClick: () =>
        showConfirmDialog({
          title: `Удалить коллекцию «${collection.name}»?`,
          confirmLabel: 'Удалить',
          cancelLabel: 'Отмена',
          variant: 'danger',
          message: (
            <Alert
              variant="danger"
              title="Действие необратимо"
              description={
                <>
                  Коллекция и все её данные будут удалены окончательно.
                  Таблица <code>{collection.table_name}</code> будет удалена из базы данных.
                </>
              }
            />
          ),
          onConfirm: async () => {
            await deleteMutation.mutateAsync(collection.id);
          },
        }),
    },
  ];

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.errorState}>Не удалось загрузить коллекции</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Коллекции</h1>
            <p className={styles.subtitle}>Управление базами знаний и векторными хранилищами</p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск коллекций..."
              value={q}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setQ(event.target.value)
              }
              className={styles.search}
            />
            <Link to="/admin/collections/new">
              <Button>Создать</Button>
            </Link>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG / ИМЯ</th>
                <th>ТЕНАНТ</th>
                <th>ПОИСК</th>
                <th>ПОЛЯ</th>
                <th>ЗАПИСЕЙ</th>
                <th>СТАТУС</th>
                <th>ДЕЙСТВИЯ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td><Skeleton width={100} /></td>
                    <td><Skeleton width={150} /></td>
                    <td><Skeleton width={100} /></td>
                    <td><Skeleton width={60} /></td>
                    <td><Skeleton width={120} /></td>
                    <td><Skeleton width={60} /></td>
                    <td><Skeleton width={60} /></td>
                    <td><Skeleton width={100} /></td>
                    <td><Skeleton width={80} /></td>
                  </tr>
                ))
              ) : filteredCollections.length === 0 ? (
                <tr>
                  <td colSpan={7} className={styles.emptyState}>
                    Коллекции не найдены
                  </td>
                </tr>
              ) : (
                filteredCollections.map((collection: Collection) => (
                  <tr key={collection.id}>
                    <td>
                      <div className={styles.cellStack}>
                        <span className={styles.cellPrimary}>{collection.slug}</span>
                        <span className={styles.cellSecondary}>{collection.name}</span>
                      </div>
                    </td>
                    <td>
                      <Badge tone="info" size="small">
                        {getTenantName(collection.tenant_id)}
                      </Badge>
                    </td>
                    <td>
                      <div className={styles.searchBadges}>
                        <Badge tone="info" size="small">SQL</Badge>
                        {collection.has_vector_search && (
                          <Badge tone="warning" size="small">VECTOR</Badge>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className={styles.fieldsList}>
                        {collection.fields.slice(0, 3).map(f => (
                          <Badge key={f.name} tone="neutral" size="small">
                            {f.name}
                          </Badge>
                        ))}
                        {collection.fields.length > 3 && (
                          <Badge tone="neutral" size="small">
                            +{collection.fields.length - 3}
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td>{collection.row_count.toLocaleString()}</td>
                    <td>
                      <Badge
                        tone={collection.is_active ? 'success' : 'neutral'}
                        size="small"
                      >
                        {collection.is_active ? 'Активна' : 'Неактивна'}
                      </Badge>
                    </td>
                    <td>
                      <ActionsButton actions={getActions(collection)} />
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

export default CollectionsPage;
