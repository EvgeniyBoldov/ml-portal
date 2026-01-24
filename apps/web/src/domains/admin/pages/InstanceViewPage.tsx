/**
 * InstanceViewPage - View tool instance details
 */
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toolInstancesApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './PromptEditorPage.module.css';

export function InstanceViewPage() {
  const { id } = useParams<{ id: string }>();

  const { data: instance, isLoading, error } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <Skeleton variant="card" />
      </div>
    );
  }

  if (error || !instance) {
    return (
      <div className={styles.wrap}>
        <Alert variant="error" title="Ошибка" description="Инстанс не найден" />
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                <line x1="6" y1="6" x2="6.01" y2="6"/>
                <line x1="6" y1="18" x2="6.01" y2="18"/>
              </svg>
              {instance.tool?.name || 'Инстанс'}
            </span>
          </h1>
          <p className={styles.description}>ID: {instance.id}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link to="/admin/instances">
            <Button variant="outline">Назад</Button>
          </Link>
          <Link to={`/admin/instances/${id}/edit`}>
            <Button variant="primary">Редактировать</Button>
          </Link>
        </div>
      </div>

      <div className={styles.grid}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Основная информация</h2>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Статус</label>
            <div>
              <Badge variant={instance.is_active ? 'success' : 'secondary'}>
                {instance.is_active ? 'Активен' : 'Неактивен'}
              </Badge>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Инструмент</label>
            <p>{instance.tool?.name || instance.tool_id}</p>
          </div>

          {instance.tool?.description && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Описание инструмента</label>
              <p>{instance.tool.description}</p>
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.label}>Health Status</label>
            <div>
              {instance.health_status ? (
                <Badge variant={instance.health_status === 'healthy' ? 'success' : 'error'}>
                  {instance.health_status}
                </Badge>
              ) : (
                <span style={{ color: 'var(--color-text-secondary)' }}>Не проверялся</span>
              )}
            </div>
          </div>

          {instance.last_health_check && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Последняя проверка</label>
              <p>{new Date(instance.last_health_check).toLocaleString()}</p>
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.label}>Создан</label>
            <p>{new Date(instance.created_at).toLocaleString()}</p>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Конфигурация</h2>
            <p className={styles.cardDescription}>JSON конфигурация инстанса</p>
          </div>

          <pre className={styles.codeBlock} style={{ 
            background: 'var(--color-bg-secondary)', 
            padding: '1rem', 
            borderRadius: '8px',
            overflow: 'auto',
            fontSize: '0.875rem'
          }}>
            {JSON.stringify(instance.config || {}, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default InstanceViewPage;
