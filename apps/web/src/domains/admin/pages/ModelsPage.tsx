/**
 * ModelsPage - Реестр моделей
 * 
 * Управление LLM и Embedding моделями.
 * Единый стиль с остальными админ-реестрами.
 */
import React, { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Model } from '@shared/api/admin';
import {
  useModels,
  useUpdateModel,
  useDeleteModel,
  useHealthCheckModel,
  useHealthCheckAllModels,
} from '@shared/api/hooks/useAdmin';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import Alert from '@shared/ui/Alert';
import { ActionsButton, type ActionItem } from '@shared/ui/ActionsButton';
import { useAppStore } from '@app/store/app.store';
import styles from './RegistryPage.module.css';

const TYPE_LABELS: Record<string, string> = {
  llm_chat: 'LLM',
  embedding: 'Embedding',
  reranker: 'Reranker',
};

const STATUS_LABELS: Record<string, string> = {
  available: 'Доступна',
  deprecated: 'Устарела',
  unavailable: 'Недоступна',
  maintenance: 'Обслуживание',
};

const HEALTH_LABELS: Record<string, string> = {
  healthy: 'OK',
  degraded: 'Деградация',
  unavailable: 'Недоступна',
};

function getStatusTone(status: string): 'success' | 'warn' | 'danger' | 'neutral' {
  switch (status) {
    case 'available': return 'success';
    case 'deprecated': return 'warn';
    case 'unavailable':
    case 'maintenance': return 'danger';
    default: return 'neutral';
  }
}

function getHealthTone(health: string): 'success' | 'warn' | 'danger' | 'neutral' {
  switch (health) {
    case 'healthy': return 'success';
    case 'degraded': return 'warn';
    case 'unavailable': return 'danger';
    default: return 'neutral';
  }
}

function ModelRow({
  model,
  getActions,
}: {
  model: Model;
  getActions: (model: Model) => ActionItem[];
}) {
  return (
    <tr>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{model.alias}</span>
          <span className={styles.cellSecondary}>{model.name}</span>
        </div>
      </td>
      <td>
        <Badge tone={model.type === 'llm_chat' ? 'info' : 'success'}>
          {TYPE_LABELS[model.type] || model.type}
        </Badge>
      </td>
      <td>
        <div className={styles.cellStack}>
          <span className={styles.cellPrimary}>{model.provider}</span>
          <span className={styles.cellSecondary}>{model.provider_model_name}</span>
        </div>
      </td>
      <td>
        <Badge tone={getStatusTone(model.status)}>
          {STATUS_LABELS[model.status] || model.status}
        </Badge>
      </td>
      <td>
        {model.health_status ? (
          <div className={styles.cellStack}>
            <Badge tone={getHealthTone(model.health_status)} size="small">
              {HEALTH_LABELS[model.health_status] || model.health_status}
            </Badge>
            {model.health_latency_ms && (
              <span className={styles.cellSecondary}>
                {model.health_latency_ms}ms
              </span>
            )}
          </div>
        ) : (
          <span className={styles.muted}>—</span>
        )}
      </td>
      <td>
        {model.default_for_type ? (
          <Badge tone="success" size="small">По умолч.</Badge>
        ) : (
          <span className={styles.muted}>—</span>
        )}
      </td>
      <td>
        <ActionsButton actions={getActions(model)} />
      </td>
    </tr>
  );
}

export function ModelsPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const showConfirmDialog = useAppStore(state => state.showConfirmDialog);

  // UI state
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const filters = useAppStore(state => state.filters);
  const [pendingModelId, setPendingModelId] = useState<string | null>(null);

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  // Query params
  const queryParams = useMemo(
    () => ({
      type: (filters.models_type as string) || undefined,
      status: (filters.models_status as string) || undefined,
      search: debouncedQ || undefined,
      page: 1,
      size: 50,
    }),
    [debouncedQ, filters.models_type, filters.models_status]
  );

  // TanStack Query
  const { data, isLoading, error } = useModels(queryParams);
  const updateModelMutation = useUpdateModel();
  const deleteModelMutation = useDeleteModel();
  const healthCheckMutation = useHealthCheckModel();
  const healthCheckAllMutation = useHealthCheckAllModels();

  const models = data?.items || [];

  const handleHealthCheckAll = async () => {
    try {
      const result = await healthCheckAllMutation.mutateAsync();
      showSuccess(`Проверка завершена: ${result.healthy}/${result.total} доступно`);
    } catch (err) {
      console.error(err);
      showError('Не удалось выполнить проверку');
    }
  };

  const handleToggleDefault = async (target: Model) => {
    try {
      setPendingModelId(target.id);
      await updateModelMutation.mutateAsync({
        id: target.id,
        data: { default_for_type: !target.default_for_type },
      });
      showSuccess(
        target.default_for_type
          ? `${target.alias} больше не по умолчанию`
          : `${target.alias} установлена по умолчанию`
      );
    } catch (err) {
      console.error(err);
      showError('Не удалось обновить флаг');
    } finally {
      setPendingModelId(null);
    }
  };

  const handleToggleEnabled = async (target: Model) => {
    try {
      setPendingModelId(target.id);
      await updateModelMutation.mutateAsync({
        id: target.id,
        data: { enabled: !target.enabled },
      });
      showSuccess(
        target.enabled
          ? `${target.alias} отключена`
          : `${target.alias} включена`
      );
    } catch (err) {
      console.error(err);
      showError('Не удалось изменить статус');
    } finally {
      setPendingModelId(null);
    }
  };

  const handleHealthCheck = async (target: Model) => {
    try {
      setPendingModelId(target.id);
      await healthCheckMutation.mutateAsync({ id: target.id, force: true });
      showSuccess(`Проверка ${target.alias} завершена`);
    } catch (err) {
      console.error(err);
      showError('Проверка не удалась');
    } finally {
      setPendingModelId(null);
    }
  };

  const handleDelete = (target: Model) => {
    showConfirmDialog({
      title: 'Удаление модели',
      confirmLabel: 'Удалить',
      cancelLabel: 'Отмена',
      variant: 'danger',
      message: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <p style={{ margin: 0 }}>
            Вы уверены, что хотите удалить модель <strong>{target.alias}</strong>?
          </p>
          <div style={{ 
            padding: '12px', 
            background: 'var(--color-bg-secondary, #f5f5f5)', 
            borderRadius: '6px',
            fontSize: '13px'
          }}>
            <div><strong>Имя:</strong> {target.name}</div>
            <div><strong>Провайдер:</strong> {target.provider}</div>
            <div><strong>Тип:</strong> {target.type === 'llm_chat' ? 'LLM' : 'Embedding'}</div>
          </div>
          <Alert
            variant="danger"
            title="Это действие необратимо"
            description="Модель будет помечена как удалённая и станет недоступна для использования."
          />
        </div>
      ),
      onConfirm: async () => {
        try {
          await deleteModelMutation.mutateAsync(target.id);
          showSuccess(`Модель «${target.alias}» удалена`);
        } catch (err: any) {
          console.error(err);
          const message = err?.message || 'Не удалось удалить модель';
          showError(message);
        }
      },
    });
  };

  const getActions = (model: Model): ActionItem[] => {
    const actions: ActionItem[] = [
      {
        label: 'Редактировать',
        onClick: () => navigate(`/admin/models/${model.id}`),
      },
      {
        label: model.enabled ? 'Отключить' : 'Включить',
        onClick: () => handleToggleEnabled(model),
        disabled: pendingModelId === model.id,
      },
      {
        label: model.default_for_type ? 'Убрать по умолч.' : 'По умолчанию',
        onClick: () => handleToggleDefault(model),
        disabled: pendingModelId === model.id || !model.enabled,
      },
      {
        label: 'Проверить',
        onClick: () => handleHealthCheck(model),
        disabled: pendingModelId === model.id || !model.enabled,
      },
    ];
    
    // Системные модели нельзя удалять
    if (!model.is_system) {
      actions.push({
        label: 'Удалить',
        onClick: () => handleDelete(model),
        danger: true,
      });
    }
    
    return actions;
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Модели</h1>
            <p className={styles.subtitle}>
              Управление LLM и Embedding моделями
            </p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск моделей..."
              value={q}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setQ(e.target.value)}
              className={styles.search}
            />
            <Button
              variant="outline"
              onClick={handleHealthCheckAll}
              disabled={healthCheckAllMutation.isPending}
            >
              {healthCheckAllMutation.isPending ? 'Проверка...' : 'Проверить все'}
            </Button>
            <Link to="/admin/models/new">
              <Button>Добавить модель</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div className={styles.errorState}>
            Не удалось загрузить модели. Попробуйте снова.
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>АЛИАС / ИМЯ</th>
                <th>ТИП</th>
                <th>ПРОВАЙДЕР / МОДЕЛЬ</th>
                <th>СТАТУС</th>
                <th>ЗДОРОВЬЕ</th>
                <th>ПО УМОЛЧ.</th>
                <th>ДЕЙСТВИЯ</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 7 }).map((__, j) => (
                      <td key={j}>
                        <Skeleton width={j === 0 ? 200 : j === 2 ? 150 : 100} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : models.length === 0 ? (
                <tr>
                  <td colSpan={7} className={styles.emptyState}>
                    Модели не найдены. Нажмите «Добавить модель» для создания.
                  </td>
                </tr>
              ) : (
                models.map(model => (
                  <ModelRow
                    key={model.id}
                    model={model}
                    getActions={getActions}
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

export default ModelsPage;
