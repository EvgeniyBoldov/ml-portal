/**
 * useEntityEditor - Universal hook for entity CRUD operations
 * 
 * Encapsulates common logic for entity editor pages:
 * - Mode detection (create/view/edit)
 * - Form state management
 * - API mutations
 * - Navigation and breadcrumbs
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import type { EntityPageMode, BreadcrumbItem } from '@/shared/ui';

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}

function getEntityIdentity(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (typeof record.id === 'string' && record.id.length > 0) return record.id;
  if (typeof record.slug === 'string' && record.slug.length > 0) return record.slug;
  return null;
}

function getEntityLabel(value: unknown, fallback: string): string {
  if (!value || typeof value !== 'object') return fallback;
  const record = value as Record<string, unknown>;
  if (typeof record.name === 'string' && record.name.length > 0) return record.name;
  if (typeof record.login === 'string' && record.login.length > 0) return record.login;
  return fallback;
}

export interface EntityEditorConfig<T, TCreate, TUpdate> {
  // Entity identification
  entityType: string;
  entityNameLabel: string;
  entityTypeLabel: string;
  
  // Paths
  basePath: string;
  listPath: string;
  
  // API
  api: {
    get: (id: string) => Promise<T>;
    create: (data: TCreate) => Promise<unknown>;
    update: (id: string, data: TUpdate) => Promise<unknown>;
    delete?: (id: string) => Promise<void>;
  };
  
  // Query keys
  queryKeys: {
    list: QueryKey;
    detail: (id: string) => QueryKey;
  };
  
  // Form configuration
  getInitialFormData: (entity?: T) => any;
  validateCreate?: (data: any) => string | null;
  validateUpdate?: (data: any) => string | null;
  transformCreate?: (data: any) => TCreate;
  transformUpdate?: (data: any) => TUpdate;
  
  // Messages
  messages: {
    create: string;
    update: string;
    delete?: string;
  };
}

export function useEntityEditor<T, TCreate = unknown, TUpdate = unknown>(config: EntityEditorConfig<T, TCreate, TUpdate>) {
  const navigate = useNavigate();
  const { id, slug } = useParams<{ id?: string; slug?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // Mode detection
  const entityIdentifier = id || slug;
  const isNew = !entityIdentifier || entityIdentifier === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';

  // Form state
  const [formData, setFormData] = useState(() => config.getInitialFormData());
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Load entity data
  const { data: entity, isLoading } = useQuery({
    queryKey: config.queryKeys.detail(entityIdentifier!),
    queryFn: () => config.api.get(entityIdentifier!),
    enabled: !!entityIdentifier && !isNew,
  });

  // Sync form with entity data
  useEffect(() => {
    if (entity) {
      setFormData(config.getInitialFormData(entity));
    } else if (isNew) {
      setFormData(config.getInitialFormData());
    }
  }, [entity, isNew]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: TCreate) => config.api.create(data),
    onSuccess: (created) => {
      // For models, invalidate ALL list queries (with any filters) using prefix
      if (config.entityType === 'model') {
        queryClient.invalidateQueries({ queryKey: ['admin', 'models', 'list'] });
      } else {
        queryClient.invalidateQueries({ queryKey: config.queryKeys.list as QueryKey });
      }
      showSuccess(config.messages.create);
      const newId = getEntityIdentity(created);
      if (!newId) {
        showError('Сущность создана, но API не вернул id/slug для перехода');
        return;
      }
      navigate(`${config.basePath}/${newId}`);
    },
    onError: (err: unknown) => showError(getErrorMessage(err, 'Ошибка создания')),
  });

  const updateMutation = useMutation({
    mutationFn: (data: TUpdate) => config.api.update(entityIdentifier!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: config.queryKeys.detail(entityIdentifier!) });
      // For models, invalidate ALL list queries (with any filters) using prefix
      if (config.entityType === 'model') {
        queryClient.invalidateQueries({ queryKey: ['admin', 'models', 'list'] });
      } else {
        queryClient.invalidateQueries({ queryKey: config.queryKeys.list as QueryKey });
      }
      showSuccess(config.messages.update);
      setSearchParams({});
    },
    onError: (err: unknown) => showError(getErrorMessage(err, 'Ошибка обновления')),
  });

  const deleteMutation = useMutation({
    mutationFn: (): Promise<void> => config.api.delete ? config.api.delete(entityIdentifier!) : Promise.resolve(),
    onSuccess: () => {
      // For models, invalidate ALL list queries (with any filters) using prefix
      if (config.entityType === 'model') {
        queryClient.invalidateQueries({ queryKey: ['admin', 'models', 'list'] });
      } else {
        queryClient.invalidateQueries({ queryKey: config.queryKeys.list as QueryKey });
      }
      if (config.messages.delete) {
        showSuccess(config.messages.delete);
      }
      navigate(config.listPath);
    },
    onError: (err: unknown) => showError(getErrorMessage(err, 'Ошибка удаления')),
  });

  // Handlers
  const handleFieldChange = (key: string, value: unknown) => {
    setFormData((prev: unknown) => ({ ...(prev as Record<string, unknown>), [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        // Validate create
        const validationError = config.validateCreate?.(formData);
        if (validationError) {
          showError(validationError);
          return;
        }
        
        const transformedData = config.transformCreate?.(formData) || formData;
        await createMutation.mutateAsync(transformedData);
      } else {
        // Validate update
        const validationError = config.validateUpdate?.(formData);
        if (validationError) {
          showError(validationError);
          return;
        }
        
        const transformedData = config.transformUpdate?.(formData) || formData;
        await updateMutation.mutateAsync(transformedData);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate(config.listPath);
    } else {
      if (entity) {
        setFormData(config.getInitialFormData(entity));
      }
      setSearchParams({});
    }
  };

  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
    if (config.api.delete) {
      await deleteMutation.mutateAsync();
    }
  };

  // Breadcrumbs
  const breadcrumbs: BreadcrumbItem[] = [
    { label: config.entityNameLabel, href: config.listPath },
    { label: getEntityLabel(entity, `Новый ${config.entityTypeLabel}`) },
  ];

  return {
    // State
    mode,
    formData,
    entity,
    isLoading,
    saving,
    showDeleteConfirm,
    breadcrumbs,
    
    // Handlers
    handleFieldChange,
    handleSave,
    handleEdit,
    handleCancel,
    handleDelete,
    handleDeleteConfirm,
    setShowDeleteConfirm,
    
    // Computed
    isNew,
    isEditable: mode === 'edit' || mode === 'create',
    canDelete: !!config.api.delete,
  };
}
