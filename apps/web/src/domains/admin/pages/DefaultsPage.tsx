/**
 * DefaultsPage - Global defaults for instances and credentials
 * Similar to tenant settings but for system-wide defaults
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, permissionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

export function DefaultsPage() {
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // Load default instances (scope=default)
  const { data: instances, isLoading: instancesLoading } = useQuery({
    queryKey: qk.toolInstances.list({ scope: 'default' }),
    queryFn: () => toolInstancesApi.list({ scope: 'default' }),
  });

  // Load default policy
  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: qk.permissions.list({ scope: 'default' }),
    queryFn: () => permissionsApi.list({ scope: 'default' }),
  });

  const defaultPolicy = policies?.find(p => p.scope === 'default');

  const isLoading = instancesLoading || policiesLoading;

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <Skeleton variant="card" />
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Общие настройки</h1>
          <p className={styles.description}>
            Настройки по умолчанию для всех пользователей системы
          </p>
        </div>
      </div>

      <div className={styles.grid}>
        {/* Default Policy */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Политика по умолчанию</h2>
            <p className={styles.cardDescription}>
              Базовые права доступа для всех пользователей
            </p>
          </div>

          {defaultPolicy ? (
            <>
              <div className={styles.formGroup}>
                <label className={styles.label}>Статус</label>
                <Badge variant={defaultPolicy.is_active ? 'success' : 'secondary'}>
                  {defaultPolicy.is_active ? 'Активна' : 'Неактивна'}
                </Badge>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.label}>Разрешённые инструменты</label>
                {defaultPolicy.allowed_tools?.length ? (
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {defaultPolicy.allowed_tools.map(tool => (
                      <Badge key={tool} variant="success">{tool}</Badge>
                    ))}
                  </div>
                ) : (
                  <span style={{ color: 'var(--color-text-secondary)' }}>Нет</span>
                )}
              </div>

              <div className={styles.formGroup}>
                <label className={styles.label}>Разрешённые коллекции</label>
                {defaultPolicy.allowed_collections?.length ? (
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {defaultPolicy.allowed_collections.map(coll => (
                      <Badge key={coll} variant="success">{coll}</Badge>
                    ))}
                  </div>
                ) : (
                  <span style={{ color: 'var(--color-text-secondary)' }}>Нет</span>
                )}
              </div>

              <div className={styles.actions}>
                <Button
                  variant="outline"
                  onClick={() => window.location.href = `/admin/policies/${defaultPolicy.id}/edit`}
                >
                  Редактировать политику
                </Button>
              </div>
            </>
          ) : (
            <Alert
              variant="warning"
              title="Политика не найдена"
              description="Создайте политику по умолчанию для базовых прав доступа"
            />
          )}
        </div>

        {/* Default Instances */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Инстансы по умолчанию</h2>
            <p className={styles.cardDescription}>
              Инстансы инструментов, доступные всем пользователям
            </p>
          </div>

          {instances?.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {instances.map(instance => (
                <div
                  key={instance.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.75rem',
                    background: 'var(--color-bg-secondary)',
                    borderRadius: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                      <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                      <line x1="6" y1="6" x2="6.01" y2="6"/>
                      <line x1="6" y1="18" x2="6.01" y2="18"/>
                    </svg>
                    <div>
                      <strong>{instance.tool?.name || 'Unknown'}</strong>
                      <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                        {instance.id.slice(0, 8)}...
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
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
              ))}
            </div>
          ) : (
            <Alert
              variant="info"
              title="Нет инстансов"
              description="Создайте инстансы инструментов в разделе Интеграции → Инстансы"
            />
          )}

          <div className={styles.actions} style={{ marginTop: '1rem' }}>
            <Button
              variant="outline"
              onClick={() => window.location.href = '/admin/instances/new'}
            >
              Добавить инстанс
            </Button>
          </div>
        </div>
      </div>

      {/* Info about hierarchy */}
      <Alert
        variant="info"
        title="Иерархия настроек"
        description="Настройки применяются по иерархии: Пользователь → Тенант → По умолчанию. Более специфичные настройки переопределяют общие."
        style={{ marginTop: '1.5rem' }}
      />
    </div>
  );
}

export default DefaultsPage;
