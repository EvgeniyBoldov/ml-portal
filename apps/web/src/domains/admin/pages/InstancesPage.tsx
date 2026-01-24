/**
 * InstancesPage - Tool instances management (admin creates based on technical capabilities)
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { ActionsButton } from '@/shared/ui/ActionsButton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptRegistryPage.module.css';

export function InstancesPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all');

  const { data: instances, isLoading, error } = useQuery({
    queryKey: qk.toolInstances.list({}),
    queryFn: () => toolInstancesApi.list({}),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => toolInstancesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess('Инстанс удалён');
    },
    onError: () => showError('Ошибка удаления'),
  });

  const healthCheckMutation = useMutation({
    mutationFn: (id: string) => toolInstancesApi.healthCheck(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess(`Health: ${data.status}`);
    },
    onError: () => showError('Health check failed'),
  });

  const filteredInstances = instances?.filter(inst => {
    if (filter === 'active') return inst.is_active;
    if (filter === 'inactive') return !inst.is_active;
    return true;
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
          <h1 className={styles.title}>Инстансы</h1>
          <p className={styles.description}>
            Конкретные подключения к инструментам. Создаются админом на основе технических возможностей.
          </p>
        </div>
        <Link to="/admin/instances/new">
          <Button variant="primary">Создать инстанс</Button>
        </Link>
      </div>

      <div className={styles.filters}>
        <select
          className={styles.select}
          value={filter}
          onChange={e => setFilter(e.target.value as typeof filter)}
        >
          <option value="all">Все</option>
          <option value="active">Активные</option>
          <option value="inactive">Неактивные</option>
        </select>
      </div>

      {!filteredInstances?.length ? (
        <Alert
          variant="info"
          title="Нет инстансов"
          description="Создайте первый инстанс для подключения инструмента"
        />
      ) : (
        <div className={styles.grid}>
          {filteredInstances.map(instance => (
            <div key={instance.id} className={styles.card}>
              <div className={styles.cardHeader}>
                <div className={styles.cardIcon}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                    <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                    <line x1="6" y1="6" x2="6.01" y2="6"/>
                    <line x1="6" y1="18" x2="6.01" y2="18"/>
                  </svg>
                </div>
                <div className={styles.cardMeta}>
                  <Badge variant={instance.is_active ? 'success' : 'secondary'}>
                    {instance.is_active ? 'Активен' : 'Неактивен'}
                  </Badge>
                  {instance.health_status && (
                    <Badge variant={instance.health_status === 'healthy' ? 'success' : 'error'}>
                      {instance.health_status}
                    </Badge>
                  )}
                </div>
              </div>

              <div className={styles.cardBody}>
                <h3 className={styles.cardTitle}>
                  <Link to={`/admin/instances/${instance.id}`}>
                    {instance.tool?.name || instance.tool_id.slice(0, 8)}
                  </Link>
                </h3>
                <p className={styles.cardDescription}>
                  {instance.config?.description || 'Нет описания'}
                </p>
                <div className={styles.cardDetails}>
                  <span>ID: {instance.id.slice(0, 8)}...</span>
                  {instance.last_health_check && (
                    <span>Проверка: {new Date(instance.last_health_check).toLocaleString()}</span>
                  )}
                </div>
              </div>

              <div className={styles.cardFooter}>
                <ActionsButton
                  actions={[
                    { label: 'Просмотр', onClick: () => window.location.href = `/admin/instances/${instance.id}` },
                    { label: 'Редактировать', onClick: () => window.location.href = `/admin/instances/${instance.id}/edit` },
                    { label: 'Health Check', onClick: () => healthCheckMutation.mutate(instance.id) },
                    { label: 'Удалить', onClick: () => deleteMutation.mutate(instance.id), variant: 'danger' },
                  ]}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default InstancesPage;
