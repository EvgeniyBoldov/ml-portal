/**
 * PermissionsPage - Управление правами доступа
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { permissionsApi, type PermissionSet } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { ActionsButton, type ActionItem } from '@/shared/ui/ActionsButton';
import { useAppStore } from '@/app/store/app.store';
import styles from './RegistryPage.module.css';

const SCOPE_LABELS: Record<string, string> = {
  default: 'По умолчанию',
  tenant: 'Тенант',
  user: 'Пользователь',
};

function PermissionRow({ 
  permission, 
  getActions,
}: { 
  permission: PermissionSet;
  getActions: (p: PermissionSet) => ActionItem[];
}) {
  const allowedCount = permission.allowed_tools.length + permission.allowed_collections.length;
  const deniedCount = permission.denied_tools.length + permission.denied_collections.length;

  return (
    <tr>
      <td>
        <Badge tone="info">{SCOPE_LABELS[permission.scope] || permission.scope}</Badge>
      </td>
      <td>
        <span className={styles.cellSecondary}>
          {permission.tenant_id ? permission.tenant_id.slice(0, 8) + '...' : '—'}
        </span>
      </td>
      <td>
        <span className={styles.cellSecondary}>
          {permission.user_id ? permission.user_id.slice(0, 8) + '...' : '—'}
        </span>
      </td>
      <td>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Badge tone="success" size="small">{allowedCount} разрешено</Badge>
          <Badge tone="danger" size="small">{deniedCount} запрещено</Badge>
        </div>
      </td>
      <td>
        <span className={styles.muted}>
          {new Date(permission.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
      <td>
        <ActionsButton actions={getActions(permission)} />
      </td>
    </tr>
  );
}

export function PermissionsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  
  const [scopeFilter, setScopeFilter] = useState<string>('');
  
  const { data: permissions, isLoading, error } = useQuery({
    queryKey: qk.permissions.list({ scope: scopeFilter || undefined }),
    queryFn: () => permissionsApi.list({ scope: scopeFilter || undefined }),
    staleTime: 60000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => permissionsApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.permissions.all() }),
  });

  const handleDelete = (permission: PermissionSet) => {
    showConfirmDialog({
      title: 'Удалить набор прав?',
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Набор прав будет удалён"
          description="Пользователи потеряют соответствующие права доступа."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteMutation.mutateAsync(permission.id);
          showSuccess('Набор прав удалён');
        } catch {
          showError('Не удалось удалить');
        }
      },
    });
  };

  const getActions = (permission: PermissionSet): ActionItem[] => [
    { label: 'Редактировать', onClick: () => navigate(`/admin/permissions/${permission.id}`) },
    { label: 'Удалить', onClick: () => handleDelete(permission), danger: true },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Права доступа</h1>
            <p className={styles.subtitle}>Управление правами на инструменты и коллекции</p>
          </div>
          <div className={styles.controls}>
            <select 
              value={scopeFilter} 
              onChange={(e) => setScopeFilter(e.target.value)}
              className={styles.search}
            >
              <option value="">Все scope</option>
              <option value="default">Default</option>
              <option value="tenant">Tenant</option>
              <option value="user">User</option>
            </select>
            <Link to="/admin/permissions/new">
              <Button>Создать</Button>
            </Link>
          </div>
        </div>

        {error && <div className={styles.errorState}>Не удалось загрузить данные</div>}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SCOPE</th>
                <th>TENANT</th>
                <th>USER</th>
                <th>ПРАВА</th>
                <th>ОБНОВЛЁН</th>
                <th>ДЕЙСТВИЯ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <td key={j}><Skeleton width={80} /></td>
                    ))}
                  </tr>
                ))
              ) : !permissions?.length ? (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    Наборы прав не найдены
                  </td>
                </tr>
              ) : (
                permissions.map(p => (
                  <PermissionRow key={p.id} permission={p} getActions={getActions} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default PermissionsPage;
