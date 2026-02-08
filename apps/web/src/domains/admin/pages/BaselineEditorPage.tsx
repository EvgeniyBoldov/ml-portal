/**
 * BaselineEditorPage - View/Edit baseline container with versions
 * 
 * REFACTORED ARCHITECTURE:
 * - Uses EntityTabsPage for unified layout
 * - Uses PromptVersionCard (baseline uses same template structure)
 * - Reduced from 396 lines to ~120 lines
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { baselinesApi, type BaselineDetail, type BaselineVersionInfo } from '@/shared/api/baselines';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityTabsPage, PromptVersionCard, Badge, type FieldDefinition, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui';

export function BaselineEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
    scope: 'default' as 'default' | 'tenant' | 'user',
    is_active: true,
  });

  // Load baseline container
  const { data: baseline, isLoading } = useQuery({
    queryKey: qk.baselines.detail(slug!),
    queryFn: () => baselinesApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  // Load active version for preview
  const activeVersion = baseline?.versions?.find(v => v.status === 'active') || baseline?.versions?.[0];
  const { data: selectedVersion } = useQuery({
    queryKey: ['baselines', slug, 'versions', activeVersion?.version],
    queryFn: () => baselinesApi.getVersion(slug!, String(activeVersion!.version)),
    enabled: !!slug && !!activeVersion,
  });

  // Sync form data
  useEffect(() => {
    if (baseline) {
      setFormData({
        slug: baseline.slug,
        name: baseline.name,
        description: baseline.description || '',
        scope: baseline.scope,
        is_active: baseline.is_active,
      });
    }
  }, [baseline]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: any) => baselinesApi.createContainer(data),
    onSuccess: (container: BaselineDetail) => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн создан');
      navigate(`/admin/baselines/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => baselinesApi.updateContainer(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.baselines.list() });
      showSuccess('Бейслайн обновлён');
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  const setRecommendedMutation = useMutation({
    mutationFn: (version: BaselineVersionInfo) => baselinesApi.setRecommendedVersion(slug!, version.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.baselines.detail(slug!) });
      showSuccess('Основная версия установлена');
    },
    onError: (err: any) => showError(err?.message || 'Ошибка установки основной версии'),
  });

  // Handlers
  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        if (!formData.slug.trim() || !formData.name.trim()) {
          showError('Заполните все обязательные поля');
          return;
        }
        await createMutation.mutateAsync(formData);
      } else {
        await updateMutation.mutateAsync({
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
        });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });
  
  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/baselines');
    } else {
      if (baseline) {
        setFormData({
          slug: baseline.slug,
          name: baseline.name,
          description: baseline.description || '',
          scope: baseline.scope,
          is_active: baseline.is_active,
        });
      }
      setSearchParams({});
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const containerFields: FieldDefinition[] = [
    {
      key: 'slug',
      label: 'Slug (ID)',
      type: 'text',
      required: true,
      disabled: !isNew,
      placeholder: 'security.no-code',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Запрет генерации кода',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Ограничения для агента...',
      rows: 2,
    },
    {
      key: 'scope',
      label: 'Scope',
      type: 'select',
      disabled: !isNew,
      options: [
        { value: 'default', label: 'Default (глобальный)' },
        { value: 'tenant', label: 'Tenant (для тенанта)' },
        { value: 'user', label: 'User (для пользователя)' },
      ],
    },
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Бейслайны', href: '/admin/baselines' },
    { label: baseline?.name || 'Новый бейслайн' },
  ];

  return (
    <EntityTabsPage
      entityType="baseline"
      entityNameLabel="Бейслайн"
      entityTypeLabel="бейслайна"
      slug={slug!}
      basePath="/admin/baselines"
      listPath="/admin/baselines"
      container={baseline || null}
      versions={baseline?.versions || []}
      isLoading={isLoading}
      formData={formData}
      mode={mode}
      saving={saving}
      onFieldChange={handleFieldChange}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onCreateVersion={() => navigate(`/admin/baselines/${slug}/versions/new`)}
      onSelectVersion={(v: BaselineVersionInfo) => navigate(`/admin/baselines/${slug}/versions/${v.version}`)}
      onSetRecommended={(v: BaselineVersionInfo) => setRecommendedMutation.mutate(v)}
      containerFields={containerFields}
      breadcrumbs={breadcrumbs}
      statusBadge={
        !isNew && baseline ? (
          <Badge tone={baseline.is_active ? 'success' : 'neutral'} size="small">
            {baseline.is_active ? 'Активен' : 'Неактивен'}
          </Badge>
        ) : undefined
      }
      renderVersionContent={() => (
        <PromptVersionCard
          version={selectedVersion || null}
          onCreateVersion={() => navigate(`/admin/baselines/${slug}/versions/new`)}
        />
      )}
    />
  );
}

export default BaselineEditorPage;
