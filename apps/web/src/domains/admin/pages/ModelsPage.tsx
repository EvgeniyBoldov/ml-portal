/**
 * ModelsPage - Admin models management
 * Uses TanStack Query for data fetching and Zustand for UI state
 */
import React, { useMemo, useState } from 'react';
import type { ModelRegistry } from '@shared/api/admin';
import {
  useModels,
  useScanModels,
  useRetireModel,
  useModelTenants,
  useUpdateModel,
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

// Component for rendering a single model row with tenants
function ModelRow({
  model,
  getActions,
  getStateColor,
}: {
  model: ModelRegistry;
  getActions: (model: ModelRegistry) => ActionItem[];
  getStateColor: (state: string) => string;
}) {
  const { data: tenantsData } = useModelTenants(model.id);
  const tenants = tenantsData?.tenants || [];

  return (
    <tr>
      <td>{model.model}</td>
      <td>{model.version}</td>
      <td>
        <Badge tone={getStateColor(model.state)}>{model.state}</Badge>
      </td>
      <td>{model.modality}</td>
      <td>
        {model.global ? (
          <Badge tone="success">Yes</Badge>
        ) : (
          <span className={styles.muted}>No</span>
        )}
      </td>
      <td>
        {tenants.length > 0 ? (
          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
            {tenants.slice(0, 3).map(tenant => (
              <Badge key={tenant.id} tone="info" size="small">
                {tenant.name}
              </Badge>
            ))}
            {tenants.length > 3 && (
              <Badge tone="neutral" size="small">
                +{tenants.length - 3}
              </Badge>
            )}
          </div>
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

type ModelTenantInfo = {
  id: string;
  name: string;
  usage_type: string;
};

export function ModelsPage() {
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // UI state
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const filters = useAppStore((state: AppState) => state.filters);
  const retireModalOpen = useAppStore(
    (state: AppState) => state.modals.retireModal || false
  );

  const openRetireModal = () => useAppStore.getState().openModal('retireModal');
  const closeRetireModal = () =>
    useAppStore.getState().closeModal('retireModal');

  const [retireOptions, setRetireOptions] = useState({
    dropVectors: false,
    removeFromTenants: false,
  });
  const [selectedModel, setSelectedModel] = useState<ModelRegistry | null>(
    null
  );
  const [pendingModelId, setPendingModelId] = useState<string | null>(null);

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  // Query params
  const queryParams = useMemo(
    () => ({
      state: filters.models_state || undefined,
      modality: filters.models_modality || undefined,
      search: debouncedQ || undefined,
      page: 1,
      size: 20,
    }),
    [debouncedQ, filters.models_state, filters.models_modality]
  );

  // TanStack Query
  const { data, isLoading, error } = useModels(queryParams);
  const scanMutation = useScanModels();
  const retireMutation = useRetireModel();
  const updateModelMutation = useUpdateModel();

  const models = data?.items || [];

  const handleToggleGlobal = async (target: ModelRegistry) => {
    try {
      setPendingModelId(target.id);
      await updateModelMutation.mutateAsync({
        id: target.id,
        data: { global: !target.global },
      });
      showSuccess(
        target.global
          ? `${target.model} is no longer global`
          : `${target.model} set as global`
      );
    } catch (error) {
      console.error(error);
      showError('Failed to update global flag');
    } finally {
      setPendingModelId(null);
    }
  };

  // Actions
  const handleScan = async () => {
    try {
      await scanMutation.mutateAsync();
      showSuccess('Models scanned successfully');
    } catch {
      showError('Failed to scan models');
    }
  };

  const handleRetire = async () => {
    if (!selectedModel) return;

    try {
      await retireMutation.mutateAsync({
        id: selectedModel.id,
        drop_vectors: retireOptions.dropVectors,
        remove_from_tenants: retireOptions.removeFromTenants,
      });
      showSuccess('Model retired successfully');
      closeRetireModal();
    } catch {
      showError('Failed to retire model');
    }
  };

  const getActions = (model: ModelRegistry): ActionItem[] => [
    {
      label: model.global ? 'Unset Global' : 'Set Global',
      onClick: () => handleToggleGlobal(model),
      disabled: pendingModelId === model.id,
    },
    {
      label: 'View Tenants',
      onClick: () => {
        setSelectedModel(model);
        useAppStore.getState().openModal('tenantsModal');
      },
    },
    {
      label: 'Retire',
      onClick: () => {
        setSelectedModel(model);
        openRetireModal();
      },
      danger: true,
    },
  ];

  const getStateColor = (state: string) => {
    switch (state) {
      case 'active':
        return 'success';
      case 'deprecated':
        return 'warn';
      case 'disabled':
        return 'danger';
      default:
        return 'neutral';
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
            <Button onClick={handleScan} disabled={scanMutation.isPending}>
              {scanMutation.isPending ? 'Scanning...' : 'Scan Models'}
            </Button>
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
                <th>MODEL</th>
                <th>VERSION</th>
                <th>STATE</th>
                <th>MODALITY</th>
                <th>GLOBAL</th>
                <th>TENANTS</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td>
                      <Skeleton width={200} />
                    </td>
                    <td>
                      <Skeleton width={100} />
                    </td>
                    <td>
                      <Skeleton width={80} />
                    </td>
                    <td>
                      <Skeleton width={100} />
                    </td>
                    <td>
                      <Skeleton width={60} />
                    </td>
                    <td>
                      <Skeleton width={150} />
                    </td>
                    <td>
                      <Skeleton width={100} />
                    </td>
                  </tr>
                ))
              ) : models.length === 0 ? (
                <tr>
                  <td colSpan={7} className={styles.emptyState}>
                    No models found
                  </td>
                </tr>
              ) : (
                models.map(model => (
                  <ModelRow
                    key={model.id}
                    model={model}
                    getActions={getActions}
                    getStateColor={getStateColor}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Retire Modal */}
      <Modal
        open={retireModalOpen}
        onClose={closeRetireModal}
        title="Retire Model"
        content={
          <div>
            <p>Are you sure you want to retire {selectedModel?.model}?</p>
            <label>
              <input
                type="checkbox"
                checked={retireOptions.dropVectors}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setRetireOptions(prev => ({
                    ...prev,
                    dropVectors: event.target.checked,
                  }))
                }
              />
              Drop vectors
            </label>
            <label>
              <input
                type="checkbox"
                checked={retireOptions.removeFromTenants}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setRetireOptions(prev => ({
                    ...prev,
                    removeFromTenants: event.target.checked,
                  }))
                }
              />
              Remove from tenants
            </label>
            <div className={styles.modalActions}>
              <Button onClick={closeRetireModal}>Cancel</Button>
              <Button
                onClick={handleRetire}
                variant="danger"
                disabled={retireMutation.isPending}
              >
                {retireMutation.isPending ? 'Retiring...' : 'Retire'}
              </Button>
            </div>
          </div>
        }
      />
    </div>
  );
}

export default ModelsPage;
