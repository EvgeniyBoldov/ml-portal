/**
 * ModelsPage - Admin models management (New Architecture)
 * 
 * Supports LLM and Embedding models only.
 * No file scanning - models are added manually via API.
 */
import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Model } from '@shared/api/admin';
import {
  useModels,
  useCreateModel,
  useUpdateModel,
  useDeleteModel,
  useHealthCheckModel,
} from '@shared/api/hooks/useAdmin';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Badge from '@shared/ui/Badge';
import { Skeleton } from '@shared/ui/Skeleton';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import Modal from '@shared/ui/Modal';
import { ActionsButton, type ActionItem } from '@shared/ui/ActionsButton';
import { useAppStore } from '@app/store/app.store';
import styles from './ModelsPage.module.css';

// Component for rendering a single model row
function ModelRow({
  model,
  getActions,
  getStatusColor,
  getTypeLabel,
}: {
  model: Model;
  getActions: (model: Model) => ActionItem[];
  getStatusColor: (status: string) => string;
  getTypeLabel: (type: string) => string;
}) {
  const healthColor = model.health_status === 'healthy' ? 'success' 
    : model.health_status === 'degraded' ? 'warn'
    : model.health_status === 'unavailable' ? 'danger'
    : 'neutral';

  return (
    <tr>
      <td>
        <div>
          <div style={{ fontWeight: 500 }}>{model.alias}</div>
          <div style={{ fontSize: '0.85em', color: '#666' }}>{model.name}</div>
        </div>
      </td>
      <td>
        <Badge tone={getTypeLabel(model.type) === 'LLM' ? 'info' : 'success'}>
          {getTypeLabel(model.type)}
        </Badge>
      </td>
      <td>
        <div>
          <div style={{ fontWeight: 500 }}>{model.provider}</div>
          <div style={{ fontSize: '0.85em', color: '#666' }}>{model.provider_model_name}</div>
        </div>
      </td>
      <td>
        <Badge tone={getStatusColor(model.status)}>{model.status}</Badge>
      </td>
      <td>
        {model.health_status ? (
          <div>
            <Badge tone={healthColor} size="small">{model.health_status}</Badge>
            {model.health_latency_ms && (
              <span style={{ fontSize: '0.85em', color: '#666', marginLeft: '4px' }}>
                ({model.health_latency_ms}ms)
              </span>
            )}
          </div>
        ) : (
          <span className={styles.muted}>—</span>
        )}
      </td>
      <td>
        {model.default_for_type ? (
          <Badge tone="success" size="small">Default</Badge>
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

type AppState = ReturnType<typeof useAppStore.getState>;

export function ModelsPage() {
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // UI state
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const filters = useAppStore((state: AppState) => state.filters);
  
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [pendingModelId, setPendingModelId] = useState<string | null>(null);

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  // Query params
  const queryParams = useMemo(
    () => ({
      type: filters.models_type || undefined,
      status: filters.models_status || undefined,
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

  const models = data?.items || [];

  const handleToggleDefault = async (target: Model) => {
    try {
      setPendingModelId(target.id);
      await updateModelMutation.mutateAsync({
        id: target.id,
        data: { default_for_type: !target.default_for_type },
      });
      showSuccess(
        target.default_for_type
          ? `${target.alias} is no longer default`
          : `${target.alias} set as default`
      );
    } catch (error) {
      console.error(error);
      showError('Failed to update default flag');
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
          ? `${target.alias} disabled`
          : `${target.alias} enabled`
      );
    } catch (error) {
      console.error(error);
      showError('Failed to toggle enabled status');
    } finally {
      setPendingModelId(null);
    }
  };

  const handleHealthCheck = async (target: Model) => {
    try {
      setPendingModelId(target.id);
      await healthCheckMutation.mutateAsync({ id: target.id, force: true });
      showSuccess(`Health check completed for ${target.alias}`);
    } catch (error) {
      console.error(error);
      showError('Health check failed');
    } finally {
      setPendingModelId(null);
    }
  };

  const handleDelete = async () => {
    if (!selectedModel) return;

    try {
      await deleteModelMutation.mutateAsync(selectedModel.id);
      showSuccess('Model deleted successfully');
      setDeleteModalOpen(false);
      setSelectedModel(null);
    } catch {
      showError('Failed to delete model');
    }
  };

  const getActions = (model: Model): ActionItem[] => [
    {
      label: model.enabled ? 'Disable' : 'Enable',
      onClick: () => handleToggleEnabled(model),
      disabled: pendingModelId === model.id,
    },
    {
      label: model.default_for_type ? 'Unset Default' : 'Set as Default',
      onClick: () => handleToggleDefault(model),
      disabled: pendingModelId === model.id || !model.enabled,
    },
    {
      label: 'Health Check',
      onClick: () => handleHealthCheck(model),
      disabled: pendingModelId === model.id || !model.enabled,
    },
    {
      label: 'Delete',
      onClick: () => {
        setSelectedModel(model);
        setDeleteModalOpen(true);
      },
      danger: true,
    },
  ];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'available':
        return 'success';
      case 'deprecated':
        return 'warn';
      case 'unavailable':
      case 'maintenance':
        return 'danger';
      default:
        return 'neutral';
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'llm_chat':
        return 'LLM';
      case 'embedding':
        return 'Embedding';
      default:
        return type;
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>Models</h1>
          <div className={styles.controls}>
            <Input
              placeholder="Search models..."
              value={q}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setQ(event.target.value)
              }
              className={styles.search}
            />
            <Link to="/admin/models/new">
              <Button>Add Model</Button>
            </Link>
          </div>
        </div>

        {error && (
          <div className={styles.errorState}>
            Failed to load models. Please try again.
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ALIAS / NAME</th>
                <th>TYPE</th>
                <th>PROVIDER / MODEL</th>
                <th>STATUS</th>
                <th>HEALTH</th>
                <th>DEFAULT</th>
                <th>ACTIONS</th>
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
                    No models found. Click "Add Model" to create one.
                  </td>
                </tr>
              ) : (
                models.map(model => (
                  <ModelRow
                    key={model.id}
                    model={model}
                    getActions={getActions}
                    getStatusColor={getStatusColor}
                    getTypeLabel={getTypeLabel}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Delete Modal */}
      <Modal
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Delete Model"
        content={
          <div>
            <p>Are you sure you want to delete <strong>{selectedModel?.alias}</strong>?</p>
            <p style={{ fontSize: '0.9em', color: '#666', marginTop: '8px' }}>
              This action cannot be undone. The model will be soft-deleted.
            </p>
            <div className={styles.modalActions}>
              <Button onClick={() => setDeleteModalOpen(false)}>Cancel</Button>
              <Button
                onClick={handleDelete}
                variant="danger"
                disabled={deleteModelMutation.isPending}
              >
                {deleteModelMutation.isPending ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        }
      />

      {/* Create Modal - TODO: Implement form */}
      <Modal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Add Model"
        content={
          <div>
            <p>Model creation form coming soon...</p>
            <div className={styles.modalActions}>
              <Button onClick={() => setCreateModalOpen(false)}>Close</Button>
            </div>
          </div>
        }
      />
    </div>
  );
}

export default ModelsPage;
