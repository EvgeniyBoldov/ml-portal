/**
 * InstanceEditorPage - Create/Edit tool instance (simplified - no tenant/priority)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolInstancesApi, toolsApi, type ToolInstanceCreate } from '@/shared/api';
import { qk } from '@/shared/api/keys';
import Button from '@/shared/ui/Button';
import Input from '@/shared/ui/Input';
import Textarea from '@/shared/ui/Textarea';
import Alert from '@/shared/ui/Alert';
import { Skeleton } from '@/shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import styles from './PromptEditorPage.module.css';

export function InstanceEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !id || id === 'new';

  const [formData, setFormData] = useState<ToolInstanceCreate>({
    tool_id: '',
    scope: 'default',
    is_active: true,
    config: {},
  });

  const [configText, setConfigText] = useState('{}');

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
        is_active: existingInstance.is_active,
        config: existingInstance.config || {},
      });
      setConfigText(JSON.stringify(existingInstance.config || {}, null, 2));
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
      navigate('/admin/instances');
    },
    onError: () => showError('Ошибка сохранения'),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const config = JSON.parse(configText);
      saveMutation.mutate({ ...formData, config });
    } catch {
      showError('Невалидный JSON в конфигурации');
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
            {isNew ? 'Создать инстанс' : 'Редактировать инстанс'}
          </h1>
          <p className={styles.description}>
            Инстанс - конкретное подключение к инструменту с определённой конфигурацией
          </p>
        </div>
        <Link to="/admin/instances">
          <Button variant="outline">Назад</Button>
        </Link>
      </div>

      <form onSubmit={handleSubmit} className={styles.grid}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Основные параметры</h2>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Инструмент *</label>
            <select
              className={styles.select}
              value={formData.tool_id}
              onChange={e => setFormData({ ...formData, tool_id: e.target.value })}
              required
            >
              <option value="">Выберите инструмент</option>
              {tools?.map(tool => (
                <option key={tool.id} value={tool.id}>
                  {tool.name} ({tool.slug})
                </option>
              ))}
            </select>
            <p className={styles.description}>
              Инструмент, для которого создаётся инстанс
            </p>
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
            <p className={styles.description}>
              Неактивные инстансы не используются при выполнении запросов
            </p>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Конфигурация</h2>
            <p className={styles.cardDescription}>
              JSON с параметрами подключения (endpoint, timeout и т.д.)
            </p>
          </div>

          <div className={styles.formGroup}>
            <Textarea
              className={styles.editor}
              style={{ minHeight: '300px', fontFamily: 'monospace' }}
              value={configText}
              onChange={e => setConfigText(e.target.value)}
              placeholder='{"endpoint": "https://...", "timeout": 30}'
            />
          </div>

          <Alert
            variant="info"
            title="Подсказка"
            description="Конфигурация зависит от типа инструмента. Например: endpoint, timeout, max_retries, headers."
          />

          <div className={styles.actions} style={{ marginTop: '1rem' }}>
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

export default InstanceEditorPage;
