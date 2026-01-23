/**
 * ToolInstanceEditorPage - Create/Edit tool instances
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, toolsApi, type ToolInstanceCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

const SCOPES = [
  { value: 'default', label: 'Default', description: 'Базовый инстанс для всех' },
  { value: 'tenant', label: 'Tenant', description: 'Для конкретного тенанта' },
  { value: 'user', label: 'User', description: 'Для конкретного пользователя' },
];

const DEFAULT_CONFIG = {
  base_url: '',
  timeout: 30,
  headers: {}
};

export function ToolInstanceEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  
  const isNew = !id || id === 'new';

  const [formData, setFormData] = useState<ToolInstanceCreate>({
    tool_id: '',
    scope: 'default',
    tenant_id: undefined,
    user_id: undefined,
    config: DEFAULT_CONFIG,
    is_default: false,
    is_active: true,
    priority: 0,
  });

  const [configText, setConfigText] = useState(JSON.stringify(DEFAULT_CONFIG, null, 2));

  // Load tools for dropdown
  const { data: tools } = useQuery({
    queryKey: qk.tools.list(),
    queryFn: () => toolsApi.list(),
  });

  // Load existing instance if editing
  const { data: existingInstance, isLoading } = useQuery({
    queryKey: qk.toolInstances.detail(id!),
    queryFn: () => toolInstancesApi.get(id!),
    enabled: !isNew,
  });

  useEffect(() => {
    if (existingInstance) {
      setFormData({
        tool_id: existingInstance.tool_id,
        scope: existingInstance.scope,
        tenant_id: existingInstance.tenant_id,
        user_id: existingInstance.user_id,
        config: existingInstance.config,
        is_default: existingInstance.is_default,
        is_active: existingInstance.is_active,
        priority: existingInstance.priority,
      });
      setConfigText(JSON.stringify(existingInstance.config, null, 2));
    }
  }, [existingInstance]);

  const saveMutation = useMutation({
    mutationFn: (data: ToolInstanceCreate) => {
      if (isNew) return toolInstancesApi.create(data);
      return toolInstancesApi.update(id!, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.toolInstances.all() });
      showSuccess('Инстанс сохранён');
      navigate('/admin/tool-instances');
    },
    onError: () => {
      showError('Ошибка сохранения');
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const config = JSON.parse(configText);
      saveMutation.mutate({
        ...formData,
        config,
        tenant_id: formData.scope === 'tenant' || formData.scope === 'user' ? formData.tenant_id : undefined,
        user_id: formData.scope === 'user' ? formData.user_id : undefined,
      });
    } catch {
      showError('Невалидный JSON в конфигурации');
    }
  };

  if (!isNew && isLoading) {
    return <div className={styles.wrap}>Загрузка...</div>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          {isNew ? 'Создать Tool Instance' : 'Редактировать Instance'}
        </h1>
        <Link to="/admin/tool-instances">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <form onSubmit={handleSubmit} className={styles.grid}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Основные настройки</h2>
            <p className={styles.cardDescription}>Привязка к инструменту и scope</p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Инструмент</label>
            <select
              className={styles.select}
              value={formData.tool_id}
              onChange={e => setFormData({ ...formData, tool_id: e.target.value })}
              required
            >
              <option value="">Выберите инструмент</option>
              {tools?.map(t => (
                <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
              ))}
            </select>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Scope</label>
            <select
              className={styles.select}
              value={formData.scope}
              onChange={e => setFormData({ ...formData, scope: e.target.value as 'default' | 'tenant' | 'user' })}
            >
              {SCOPES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <p className={styles.description}>
              {SCOPES.find(s => s.value === formData.scope)?.description}
            </p>
          </div>

          {(formData.scope === 'tenant' || formData.scope === 'user') && (
            <div className={styles.formGroup}>
              <label className={styles.label}>Tenant ID</label>
              <Input
                value={formData.tenant_id || ''}
                onChange={e => setFormData({ ...formData, tenant_id: e.target.value || undefined })}
                placeholder="UUID тенанта"
              />
            </div>
          )}

          {formData.scope === 'user' && (
            <div className={styles.formGroup}>
              <label className={styles.label}>User ID</label>
              <Input
                value={formData.user_id || ''}
                onChange={e => setFormData({ ...formData, user_id: e.target.value || undefined })}
                placeholder="UUID пользователя"
              />
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.label}>Приоритет</label>
            <Input
              type="number"
              value={formData.priority}
              onChange={e => setFormData({ ...formData, priority: parseInt(e.target.value) || 0 })}
            />
            <p className={styles.description}>Чем выше, тем приоритетнее при выборе</p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.is_default}
                onChange={e => setFormData({ ...formData, is_default: e.target.checked })}
              />
              <span>Default instance (используется по умолчанию)</span>
            </label>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
              />
              <span>Активен</span>
            </label>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Конфигурация</h2>
            <p className={styles.cardDescription}>JSON конфиг для подключения</p>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Config (JSON)</label>
            <Textarea
              className={styles.editor}
              style={{ minHeight: '300px' }}
              value={configText}
              onChange={e => setConfigText(e.target.value)}
              placeholder='{"base_url": "https://...", "timeout": 30}'
            />
          </div>

          <div className={styles.actions}>
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

export default ToolInstanceEditorPage;
