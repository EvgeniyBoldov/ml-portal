/**
 * PoliciesPage - Permission policies management (renamed from Permissions)
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { permissionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { ActionsButton } from '@/shared/ui/ActionsButton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptRegistryPage.module.css';

const SCOPE_LABELS: Record<string, string> = {
  default: 'По умолчанию',
  tenant: 'Тенант',
  user: 'Пользователь',
};

export function PoliciesPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [scopeFilter, setScopeFilter] = useState<string>('all');

  const { data: policies, isLoading, error } = useQuery({
    queryKey: qk.permissions.list({}),
    queryFn: () => permissionsApi.list({}),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => permissionsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.all() });
      showSuccess('Политика удалена');
    },
    onError: () => showError('Ошибка удаления'),
  });

  const filteredPolicies = policies?.filter(p => {
    if (scopeFilter === 'all') return true;
    return p.scope === scopeFilter;
  });

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <Skeleton variant="card" />
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.wrap}>
        <Alert variant="error" title="Ошибка загрузки" description={String(error)} />
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Политики</h1>
          <p className={styles.description}>
            Политики доступа определяют какие инструменты и коллекции доступны пользователям
          </p>
        </div>
        <Link to="/admin/policies/new">
          <Button variant="primary">Создать политику</Button>
        </Link>
      </div>

      <div className={styles.filters}>
        <select
          className={styles.select}
          value={scopeFilter}
          onChange={e => setScopeFilter(e.target.value)}
        >
          <option value="all">Все уровни</option>
          <option value="default">По умолчанию</option>
          <option value="tenant">Тенант</option>
          <option value="user">Пользователь</option>
        </select>
      </div>

      {!filteredPolicies?.length ? (
        <Alert
          variant="info"
          title="Нет политик"
          description="Создайте политику для управления доступом к инструментам"
        />
      ) : (
        <div className={styles.list}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Уровень</th>
                <th>Тенант / Пользователь</th>
                <th>Разрешённые инструменты</th>
                <th>Разрешённые коллекции</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filteredPolicies.map(policy => (
                <tr key={policy.id}>
                  <td>
                    <Badge variant={policy.scope === 'default' ? 'primary' : 'secondary'}>
                      {SCOPE_LABELS[policy.scope] || policy.scope}
                    </Badge>
                  </td>
                  <td>
                    {policy.scope === 'default' ? (
                      <span style={{ color: 'var(--color-text-secondary)' }}>—</span>
                    ) : policy.scope === 'tenant' ? (
                      policy.tenant_id?.slice(0, 8) + '...'
                    ) : (
                      policy.user_id?.slice(0, 8) + '...'
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                      {policy.allowed_tools?.slice(0, 3).map(tool => (
                        <Badge key={tool} variant="outline">{tool}</Badge>
                      ))}
                      {(policy.allowed_tools?.length || 0) > 3 && (
                        <Badge variant="outline">+{policy.allowed_tools!.length - 3}</Badge>
                      )}
                      {!policy.allowed_tools?.length && (
                        <span style={{ color: 'var(--color-text-secondary)' }}>Нет</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                      {policy.allowed_collections?.slice(0, 2).map(coll => (
                        <Badge key={coll} variant="outline">{coll}</Badge>
                      ))}
                      {(policy.allowed_collections?.length || 0) > 2 && (
                        <Badge variant="outline">+{policy.allowed_collections!.length - 2}</Badge>
                      )}
                      {!policy.allowed_collections?.length && (
                        <span style={{ color: 'var(--color-text-secondary)' }}>Нет</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <Badge variant={policy.is_active ? 'success' : 'secondary'}>
                      {policy.is_active ? 'Активна' : 'Неактивна'}
                    </Badge>
                  </td>
                  <td>
                    <ActionsButton
                      actions={[
                        { label: 'Просмотр', onClick: () => window.location.href = `/admin/policies/${policy.id}` },
                        { label: 'Редактировать', onClick: () => window.location.href = `/admin/policies/${policy.id}/edit` },
                        { 
                          label: 'Удалить', 
                          onClick: () => deleteMutation.mutate(policy.id), 
                          variant: 'danger',
                          disabled: policy.scope === 'default'
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default PoliciesPage;
