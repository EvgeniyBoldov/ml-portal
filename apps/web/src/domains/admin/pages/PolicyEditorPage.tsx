/**
 * PolicyEditorPage - Create/Edit permission policy
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { permissionsApi, toolsApi, type PermissionSetCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

export function PolicyEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !id || id === 'new';

  const [formData, setFormData] = useState<PermissionSetCreate>({
    scope: 'default',
    tenant_id: undefined,
    user_id: undefined,
    allowed_tools: [],
    denied_tools: [],
    allowed_collections: [],
    denied_collections: [],
    is_active: true,
  });

  // Load tools for selection
  const { data: tools } = useQuery({
    queryKey: qk.tools.list(),
    queryFn: () => toolsApi.list(),
  });

  // Load existing policy if editing
  const { data: existingPolicy, isLoading } = useQuery({
    queryKey: qk.permissions.detail(id!),
    queryFn: () => permissionsApi.get(id!),
    enabled: !isNew,
  });

  useEffect(() => {
    if (existingPolicy) {
      setFormData({
        scope: existingPolicy.scope,
        tenant_id: existingPolicy.tenant_id,
        user_id: existingPolicy.user_id,
        allowed_tools: existingPolicy.allowed_tools || [],
        denied_tools: existingPolicy.denied_tools || [],
        allowed_collections: existingPolicy.allowed_collections || [],
        denied_collections: existingPolicy.denied_collections || [],
        is_active: existingPolicy.is_active,
      });
    }
  }, [existingPolicy]);

  const saveMutation = useMutation({
    mutationFn: (data: PermissionSetCreate) => {
      if (isNew) return permissionsApi.create(data);
      return permissionsApi.update(id!, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.all() });
      showSuccess('Политика сохранена');
      navigate('/admin/policies');
    },
    onError: () => showError('Ошибка сохранения'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate({
      ...formData,
      tenant_id: formData.scope === 'tenant' || formData.scope === 'user' ? formData.tenant_id : undefined,
      user_id: formData.scope === 'user' ? formData.user_id : undefined,
    });
  };

  const toggleTool = (slug: string, list: 'allowed' | 'denied') => {
    const key = list === 'allowed' ? 'allowed_tools' : 'denied_tools';
    const otherKey = list === 'allowed' ? 'denied_tools' : 'allowed_tools';
    const current = formData[key] || [];
    const other = formData[otherKey] || [];

    if (current.includes(slug)) {
      setFormData({ ...formData, [key]: current.filter(t => t !== slug) });
    } else {
      setFormData({
        ...formData,
        [key]: [...current, slug],
        [otherKey]: other.filter(t => t !== slug),
      });
    }
  };

  if (!isNew && isLoading) {
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
          <h1 className={styles.title}>
            {isNew ? 'Создать политику' : 'Редактировать политику'}
          </h1>
          <p className={styles.description}>
            Политика определяет доступ к инструментам и коллекциям
          </p>
        </div>
        <Link to="/admin/policies">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <form onSubmit={handleSubmit} className={styles.grid}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Область применения</h2>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Уровень *</label>
            <select
              className={styles.select}
              value={formData.scope}
              onChange={e => setFormData({ ...formData, scope: e.target.value as 'default' | 'tenant' | 'user' })}
              disabled={!isNew && existingPolicy?.scope === 'default'}
            >
              <option value="default">По умолчанию (для всех)</option>
              <option value="tenant">Тенант</option>
              <option value="user">Пользователь</option>
            </select>
          </div>

          {(formData.scope === 'tenant' || formData.scope === 'user') && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Tenant ID *</label>
              <Input
                value={formData.tenant_id || ''}
                onChange={e => setFormData({ ...formData, tenant_id: e.target.value || undefined })}
                placeholder="UUID тенанта"
                required
              />
            </div>
          )}

          {formData.scope === 'user' && (
            <div className={styles.formGroup}>
              <label className={styles.label}>User ID *</label>
              <Input
                value={formData.user_id || ''}
                onChange={e => setFormData({ ...formData, user_id: e.target.value || undefined })}
                placeholder="UUID пользователя"
                required
              />
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
              />
              <span>Активна</span>
            </label>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Инструменты</h2>
            <p className={styles.cardDescription}>
              Выберите разрешённые и запрещённые инструменты
            </p>
          </div>

          {tools?.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {tools.map(tool => {
                const isAllowed = formData.allowed_tools?.includes(tool.slug);
                const isDenied = formData.denied_tools?.includes(tool.slug);
                return (
                  <div
                    key={tool.slug}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.75rem',
                      background: 'var(--color-bg-secondary)',
                      borderRadius: '8px',
                    }}
                  >
                    <div>
                      <strong>{tool.name}</strong>
                      <span style={{ color: 'var(--color-text-secondary)', marginLeft: '0.5rem' }}>
                        {tool.slug}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <Button
                        type="button"
                        variant={isAllowed ? 'primary' : 'outline'}
                        size="sm"
                        onClick={() => toggleTool(tool.slug, 'allowed')}
                      >
                        ✓ Разрешить
                      </Button>
                      <Button
                        type="button"
                        variant={isDenied ? 'danger' : 'outline'}
                        size="sm"
                        onClick={() => toggleTool(tool.slug, 'denied')}
                      >
                        ✗ Запретить
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <Alert variant="info" title="Нет инструментов" description="Сначала создайте инструменты" />
          )}

          <div className={styles.actions} style={{ marginTop: '1.5rem' }}>
            <Button
              type="submit"
              variant="primary"
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

export default PolicyEditorPage;
