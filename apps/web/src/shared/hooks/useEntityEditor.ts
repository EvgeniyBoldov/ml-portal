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
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import type { EntityPageMode, BreadcrumbItem } from '@/shared/ui';

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
    create: (data: TCreate) => Promise<T>;
    update: (id: string, data: TUpdate) => Promise<T>;
    delete?: (id: string) => Promise<void>;
  };
  
  // Query keys
  queryKeys: {
    list: any[];
    detail: (id: string) => any[];
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

export function useEntityEditor<T, TCreate = any, TUpdate = any>(config: EntityEditorConfig<T, TCreate, TUpdate>) {
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
    onSuccess: (created: T) => {
      queryClient.invalidateQueries({ queryKey: config.queryKeys.list });
      showSuccess(config.messages.create);
      const newId = (created as any).id || (created as any).slug;
      navigate(`${config.basePath}/${newId}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: TUpdate) => config.api.update(entityIdentifier!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: config.queryKeys.detail(entityIdentifier!) });
      queryClient.invalidateQueries({ queryKey: config.queryKeys.list });
      showSuccess(config.messages.update);
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => config.api.delete?.(entityIdentifier!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: config.queryKeys.list });
      if (config.messages.delete) {
        showSuccess(config.messages.delete);
      }
      navigate(config.listPath);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка удаления'),
  });

  // Handlers
  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: any) => ({ ...prev, [key]: value }));
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
    { label: (entity as any)?.name || (entity as any)?.login || `Новый ${config.entityTypeLabel}` },
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
