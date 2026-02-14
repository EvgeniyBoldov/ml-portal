/**
 * ModelsPage - Реестр моделей
 * 
 * Управление LLM и Embedding моделями.
 * Единый стиль с остальными админ-реестрами.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Model } from '@shared/api/admin';
import {
  useModels,
  useUpdateModel,
  useDeleteModel,
  useHealthCheckModel,
  useHealthCheckAllModels,
} from '@shared/api/hooks/useAdmin';
import { AdminPage, DataTable, type DataTableColumn, Badge, Alert, ActionsButton, type ActionItem } from '@/shared/ui';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { useAppStore } from '@app/store/app.store';
import { getStatusProps, MODEL_TYPE_LABELS } from '@/shared/lib/statusConfig';

const HEALTH_LABELS: Record<string, string> = {
  healthy: 'OK',
  degraded: 'Деградация',
  unavailable: 'Недоступна',
};

function getHealthTone(health: string): 'success' | 'warn' | 'danger' | 'neutral' {
  switch (health) {
    case 'healthy': return 'success';
    case 'degraded': return 'warn';
    case 'unavailable': return 'danger';
    default: return 'neutral';
  }
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
    } catch (err: unknown) {
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
            background: 'var(--bg-hover, #f5f5f5)', 
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
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : 'Не удалось удалить модель';
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
        variant: 'danger',
      });
    }
    
    return actions;
  };

  const columns: DataTableColumn<Model>[] = [
    {
      key: 'alias',
      label: 'АЛИАС / ИМЯ',
      sortable: true,
      render: (model) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{model.alias}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{model.name}</span>
        </div>
      ),
    },
    {
      key: 'type',
      label: 'ТИП',
      width: 100,
      sortable: true,
      render: (model) => (
        <Badge tone={model.type === 'llm_chat' ? 'info' : 'success'}>
          {MODEL_TYPE_LABELS[model.type] || model.type}
        </Badge>
      ),
    },
    {
      key: 'provider',
      label: 'ПРОВАЙДЕР / МОДЕЛЬ',
      sortable: true,
      render: (model) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 500 }}>{model.provider}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{model.provider_model_name}</span>
          {model.instance_name && (
            <span style={{ fontSize: '0.7rem', color: 'var(--muted)', opacity: 0.7 }}>⇢ {model.instance_name}</span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      label: 'СТАТУС',
      width: 120,
      sortable: true,
      render: (model) => (
        <Badge tone={getStatusProps('model', model.status).tone}>
          {getStatusProps('model', model.status).label}
        </Badge>
      ),
    },
    {
      key: 'health_status',
      label: 'ЗДОРОВЬЕ',
      width: 100,
      sortable: true,
      render: (model) => model.health_status ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <Badge tone={getHealthTone(model.health_status)} size="small">
            {HEALTH_LABELS[model.health_status] || model.health_status}
          </Badge>
          {model.health_latency_ms && (
            <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
              {model.health_latency_ms}ms
            </span>
          )}
        </div>
      ) : (
        <span style={{ color: 'var(--muted)' }}>—</span>
      ),
    },
    {
      key: 'default_for_type',
      label: 'ПО УМОЛЧ.',
      width: 100,
      sortable: true,
      render: (model) => model.default_for_type ? (
        <Badge tone="success" size="small">По умолч.</Badge>
      ) : (
        <span style={{ color: 'var(--muted)' }}>—</span>
      ),
    },
    {
      key: 'actions',
      label: 'ДЕЙСТВИЯ',
      width: 80,
      align: 'right',
      render: (model) => <ActionsButton actions={getActions(model)} />,
    },
  ];

  return (
    <AdminPage
      title="Модели"
      subtitle="Управление LLM и Embedding моделями"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск моделей..."
      actions={[
        {
          label: healthCheckAllMutation.isPending ? 'Проверка...' : 'Проверить все',
          onClick: handleHealthCheckAll,
          disabled: healthCheckAllMutation.isPending,
          variant: 'outline',
        },
        {
          label: 'Добавить модель',
          onClick: () => navigate('/admin/models/new'),
          variant: 'primary',
        },
      ]}
    >
      {error && (
        <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: '8px', marginBottom: '16px' }}>
          Не удалось загрузить модели. Попробуйте снова.
        </div>
      )}

      <DataTable
        columns={columns}
        data={models}
        keyField="id"
        loading={isLoading}
        emptyText="Модели не найдены. Нажмите «Добавить модель» для создания."
        paginated
        pageSize={20}
        onRowClick={(model) => navigate(`/admin/models/${model.id}`)}
      />
    </AdminPage>
  );
}

export default ModelsPage;
