/**
 * CollectionsPage - Admin collections management
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { ActionsButton } from '@shared/ui/ActionsButton';
import { useAppStore } from '@app/store/app.store';
import Alert from '@shared/ui/Alert';
import { collectionsApi, type Collection } from '@shared/api/collections';
import { tenantApi } from '@shared/api/admin';
import styles from './CollectionsPage.module.css';

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
    queryFn: () => tenantApi.list({ page: 1, size: 100 }),
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

  const getActions = (collection: Collection) => [
    {
      label: 'View Details',
      onClick: () => navigate(`/admin/collections/${collection.id}`),
    },
    {
      label: 'Delete',
      danger: true,
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
        <div className={styles.errorState}>Failed to load collections.</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>Collections</h1>
          <div className={styles.controls}>
            <Input
              placeholder="Search collections..."
              value={q}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setQ(event.target.value)
              }
              className={styles.search}
            />
            <Button onClick={() => navigate('/admin/collections/new')}>
              Create Collection
            </Button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG</th>
                <th>NAME</th>
                <th>TENANT</th>
                <th>TYPE</th>
                <th>FIELDS</th>
                <th>ROWS</th>
                <th>STATUS</th>
                <th>CREATED</th>
                <th>ACTIONS</th>
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
                  <td colSpan={9} className={styles.emptyState}>
                    No collections found
                  </td>
                </tr>
              ) : (
                filteredCollections.map((collection: Collection) => (
                  <tr key={collection.id}>
                    <td>
                      <span className={styles.slug}>{collection.slug}</span>
                    </td>
                    <td>{collection.name}</td>
                    <td>
                      <span className={styles.tenantName}>
                        {getTenantName(collection.tenant_id)}
                      </span>
                    </td>
                    <td>
                      <Badge
                        tone={collection.type === 'sql' ? 'info' : 'warning'}
                        size="small"
                      >
                        {collection.type.toUpperCase()}
                      </Badge>
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
                        {collection.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td>
                      {new Date(collection.created_at).toLocaleDateString()}
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
