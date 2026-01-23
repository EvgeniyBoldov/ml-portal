/**
 * ToolInstancesPage - Реестр инстансов инструментов
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { toolInstancesApi, type ToolInstance, type ToolInstanceHealthStatus } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Input from '@/shared/ui/Input';
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

const HEALTH_TONES: Record<ToolInstanceHealthStatus, 'success' | 'danger' | 'neutral'> = {
  healthy: 'success',
  unhealthy: 'danger',
  unknown: 'neutral',
};

function InstanceRow({ 
  instance, 
  getActions,
  onHealthCheck,
}: { 
  instance: ToolInstance;
  getActions: (instance: ToolInstance) => ActionItem[];
  onHealthCheck: (instance: ToolInstance) => void;
}) {
  return (
    <tr>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{instance.slug}</span>
          <span className={styles.cellSecondary}>{instance.name}</span>
        </div>
      </td>
      <td>
        <Badge tone="info">{SCOPE_LABELS[instance.scope] || instance.scope}</Badge>
      </td>
      <td>
        <Badge 
          tone={HEALTH_TONES[instance.health_status]} 
          size="small"
          onClick={() => onHealthCheck(instance)}
          style={{ cursor: 'pointer' }}
        >
          {instance.health_status}
        </Badge>
      </td>
      <td>
        <Badge tone={instance.is_active ? 'success' : 'neutral'} size="small">
          {instance.is_active ? 'Активен' : 'Неактивен'}
        </Badge>
      </td>
      <td>
        <ActionsButton actions={getActions(instance)} />
      </td>
    </tr>
  );
}

export function ToolInstancesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);
  
  const [q, setQ] = useState('');
  
  const { data: instances, isLoading, error } = useQuery({
    queryKey: qk.toolInstances.list(),
    queryFn: () => toolInstancesApi.list(),
    staleTime: 60000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => toolInstancesApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() }),
  });

  const healthCheckMutation = useMutation({
    mutationFn: (id: string) => toolInstancesApi.healthCheck(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() }),
  });

  const filtered = instances?.filter(i => 
    i.name.toLowerCase().includes(q.toLowerCase()) || 
    i.slug.toLowerCase().includes(q.toLowerCase())
  ) || [];

  const handleDelete = (instance: ToolInstance) => {
    showConfirmDialog({
      title: `Удалить инстанс «${instance.slug}»?`,
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <Alert
          variant="danger"
          title="Инстанс будет удалён"
          description="Удаление нельзя отменить. Связанные credentials также будут удалены."
        />
      ),
      onConfirm: async () => {
        try {
          await deleteMutation.mutateAsync(instance.id);
          showSuccess(`Инстанс ${instance.slug} удалён`);
        } catch (err) {
          showError('Не удалось удалить инстанс');
        }
      },
    });
  };

  const handleHealthCheck = async (instance: ToolInstance) => {
    try {
      const result = await healthCheckMutation.mutateAsync(instance.id);
      showSuccess(`Health check: ${result.status}`);
    } catch (err) {
      showError('Health check failed');
    }
  };

  const getActions = (instance: ToolInstance): ActionItem[] => [
    { label: 'Редактировать', onClick: () => navigate(`/admin/tool-instances/${instance.id}`) },
    { label: 'Health Check', onClick: () => handleHealthCheck(instance) },
    { label: 'Удалить', onClick: () => handleDelete(instance), danger: true },
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Инстансы инструментов</h1>
            <p className={styles.subtitle}>Конкретные подключения к инструментам</p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/tool-instances/new">
              <Button>Создать инстанс</Button>
            </Link>
          </div>
        </div>

        {error && <div className={styles.errorState}>Не удалось загрузить данные</div>}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SLUG / ИМЯ</th>
                <th>SCOPE</th>
                <th>HEALTH</th>
                <th>СТАТУС</th>
                <th>ДЕЙСТВИЯ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 5 }).map((__, j) => (
                      <td key={j}><Skeleton width={100} /></td>
                    ))}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyState}>
                    Инстансы не найдены
                  </td>
                </tr>
              ) : (
                filtered.map(instance => (
                  <InstanceRow 
                    key={instance.id} 
                    instance={instance} 
                    getActions={getActions}
                    onHealthCheck={handleHealthCheck}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ToolInstancesPage;
