/**
 * PolicyViewPage - View policy details
 */
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { permissionsApi } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Badge from '@/shared/ui/Badge';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import styles from './PromptEditorPage.module.css';

const SCOPE_LABELS: Record<string, string> = {
  default: 'По умолчанию',
  tenant: 'Тенант',
  user: 'Пользователь',
};

export function PolicyViewPage() {
  const { id } = useParams<{ id: string }>();

  const { data: policy, isLoading, error } = useQuery({
    queryKey: qk.permissions.detail(id!),
    queryFn: () => permissionsApi.get(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className={styles.wrap}>
        <Skeleton variant="card" />
      </div>
    );
  }

  if (error || !policy) {
    return (
      <div className={styles.wrap}>
        <Alert variant="error" title="Ошибка" description="Политика не найдена" />
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Политика доступа</h1>
          <p className={styles.description}>ID: {policy.id}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link to="/admin/policies">
            <Button variant="outline">Назад</Button>
          </Link>
          <Link to={`/admin/policies/${id}/edit`}>
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
            <label className={styles.label}>Уровень</label>
            <div>
              <Badge variant={policy.scope === 'default' ? 'primary' : 'secondary'}>
                {SCOPE_LABELS[policy.scope] || policy.scope}
              </Badge>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Статус</label>
            <div>
              <Badge variant={policy.is_active ? 'success' : 'secondary'}>
                {policy.is_active ? 'Активна' : 'Неактивна'}
              </Badge>
            </div>
          </div>

          {policy.tenant_id && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Тенант</label>
              <p>{policy.tenant_id}</p>
            </div>
          )}

          {policy.user_id && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Пользователь</label>
              <p>{policy.user_id}</p>
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.label}>Создана</label>
            <p>{new Date(policy.created_at).toLocaleString()}</p>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Разрешения</h2>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Разрешённые инструменты</label>
            {policy.allowed_tools?.length ? (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {policy.allowed_tools.map(tool => (
                  <Badge key={tool} variant="success">{tool}</Badge>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--color-text-secondary)' }}>Нет разрешённых инструментов</p>
            )}
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Запрещённые инструменты</label>
            {policy.denied_tools?.length ? (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {policy.denied_tools.map(tool => (
                  <Badge key={tool} variant="error">{tool}</Badge>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--color-text-secondary)' }}>Нет запрещённых инструментов</p>
            )}
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Разрешённые коллекции</label>
            {policy.allowed_collections?.length ? (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {policy.allowed_collections.map(coll => (
                  <Badge key={coll} variant="success">{coll}</Badge>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--color-text-secondary)' }}>Нет разрешённых коллекций</p>
            )}
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Запрещённые коллекции</label>
            {policy.denied_collections?.length ? (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {policy.denied_collections.map(coll => (
                  <Badge key={coll} variant="error">{coll}</Badge>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--color-text-secondary)' }}>Нет запрещённых коллекций</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default PolicyViewPage;
