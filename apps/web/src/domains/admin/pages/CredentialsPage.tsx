/**
 * CredentialsPage - Управление учетными данными для инструментов
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { credentialsApi, type CredentialSet } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { ActionsButton, type ActionItem } from '@/shared/ui/ActionsButton';
import { useAppStore } from '@/app/store/app.store';
import styles from './RegistryPage.module.css';

const AUTH_TYPE_LABELS: Record<string, string> = {
  token: 'Bearer Token',
  basic: 'Basic Auth',
  oauth: 'OAuth',
  api_key: 'API Key',
};

const SCOPE_LABELS: Record<string, string> = {
  tenant: 'Тенант',
  user: 'Пользователь',
};

function CredentialRow({ 
  credential, 
  getActions,
}: { 
  credential: CredentialSet;
  getActions: (c: CredentialSet) => ActionItem[];
}) {
  return (
    <tr>
      <td>
        <span className={styles.cellSecondary}>
          {credential.tool_instance_id.slice(0, 8)}...
        </span>
      </td>
      <td>
        <Badge tone="info">{AUTH_TYPE_LABELS[credential.auth_type] || credential.auth_type}</Badge>
      </td>
      <td>
        <Badge tone="warning">{SCOPE_LABELS[credential.scope] || credential.scope}</Badge>
      </td>
      <td>
        <Badge tone={credential.is_active ? 'success' : 'neutral'} size="small">
          {credential.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      </td>
      <td>
        <span className={styles.muted}>
          {new Date(credential.updated_at).toLocaleDateString('ru-RU')}
        </span>
      </td>
      <td>
        <ActionsButton actions={getActions(credential)} />
      </td>
    </tr>
  );
}

export function CredentialsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  
  const [scopeFilter, setScopeFilter] = useState<string>('');
  
  const { data: credentials, isLoading, error } = useQuery({
    queryKey: qk.credentials.list({ scope: scopeFilter || undefined }),
    queryFn: () => credentialsApi.list({ scope: scopeFilter || undefined }),
    staleTime: 60000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => credentialsApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.credentials.all() }),
  });

  const handleDelete = (credential: CredentialSet) => {
    showConfirmDialog({
      title: 'Удалить учетные данные?',
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Учетные данные будут удалены"
          description="Инструмент потеряет доступ к внешнему сервису."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteMutation.mutateAsync(credential.id);
          showSuccess('Учетные данные удалены');
        } catch {
          showError('Не удалось удалить');
        }
      },
    });
  };

  const getActions = (credential: CredentialSet): ActionItem[] => [
    { label: 'Редактировать', onClick: () => navigate(`/admin/credentials/${credential.id}`) },
    { label: 'Удалить', onClick: () => handleDelete(credential), danger: true },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Учетные данные</h1>
            <p className={styles.subtitle}>Credentials для подключения к внешним сервисам</p>
          </div>
          <div className={styles.controls}>
            <select 
              value={scopeFilter} 
              onChange={(e) => setScopeFilter(e.target.value)}
              className={styles.search}
            >
              <option value="">Все scope</option>
              <option value="tenant">Tenant</option>
              <option value="user">User</option>
            </select>
            <Link to="/admin/credentials/new">
              <Button>Создать</Button>
            </Link>
          </div>
        </div>

        {error && <div className={styles.errorState}>Не удалось загрузить данные</div>}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>TOOL INSTANCE</th>
                <th>ТИП АВТОРИЗАЦИИ</th>
                <th>SCOPE</th>
                <th>СТАТУС</th>
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
              ) : !credentials?.length ? (
                <tr>
                  <td colSpan={6} className={styles.emptyState}>
                    Учетные данные не найдены
                  </td>
                </tr>
              ) : (
                credentials.map(c => (
                  <CredentialRow key={c.id} credential={c} getActions={getActions} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default CredentialsPage;
