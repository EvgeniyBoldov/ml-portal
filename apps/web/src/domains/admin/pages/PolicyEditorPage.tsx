/**
 * PolicyEditorPage - View/Edit policy container with versions
 * 
 * REFACTORED ARCHITECTURE:
 * - Uses EntityTabsPage for unified layout
 * - Uses PolicyVersionCard for version preview
 * - Reduced from 378 lines to ~120 lines
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyDetail, type PolicyVersionInfo } from '@/shared/api/policies';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityTabsPage, PolicyVersionCard, Badge, type FieldDefinition, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui';

export function PolicyEditorPage() {
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

  // Load policy container
  const { data: policy, isLoading } = useQuery({
    queryKey: qk.policies.detail(slug!),
    queryFn: () => policiesApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  // Load active version for preview
  const activeVersion = policy?.versions?.find(v => v.status === 'active') || policy?.versions?.[0];
  const { data: selectedVersion } = useQuery({
    queryKey: ['policies', slug, 'versions', activeVersion?.version],
    queryFn: () => policiesApi.getVersion(slug!, String(activeVersion!.version)),
    enabled: !!slug && !!activeVersion,
  });

  // Sync form data
  useEffect(() => {
    if (policy) {
      setFormData({
        slug: policy.slug,
        name: policy.name,
        description: policy.description || '',
        scope: policy.scope,
        is_active: policy.is_active,
      });
    }
  }, [policy]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: any) => policiesApi.createContainer(data),
    onSuccess: (container: PolicyDetail) => {
      queryClient.invalidateQueries({ queryKey: qk.policies.list() });
      showSuccess('Политика создана');
      navigate(`/admin/policies/${container.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => policiesApi.updateContainer(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.list() });
      showSuccess('Политика обновлена');
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

  const setRecommendedMutation = useMutation({
    mutationFn: (version: PolicyVersionInfo) => policiesApi.setRecommendedVersion(slug!, version.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
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
      navigate('/admin/policies');
    } else {
      if (policy) {
        setFormData({
          slug: policy.slug,
          name: policy.name,
          description: policy.description || '',
          scope: policy.scope,
          is_active: policy.is_active,
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
      placeholder: 'execution.strict',
      description: isNew ? 'Уникальный идентификатор (нельзя изменить после создания)' : undefined,
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Строгие лимиты выполнения',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Лимиты для агента...',
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
    { label: 'Политики', href: '/admin/policies' },
    { label: policy?.name || 'Новая политика' },
  ];

  return (
    <EntityTabsPage
      entityType="policy"
      entityNameLabel="Политика"
      entityTypeLabel="политики"
      slug={slug!}
      basePath="/admin/policies"
      listPath="/admin/policies"
      container={policy || null}
      versions={policy?.versions || []}
      isLoading={isLoading}
      formData={formData}
      mode={mode}
      saving={saving}
      onFieldChange={handleFieldChange}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onCreateVersion={() => navigate(`/admin/policies/${slug}/versions/new`)}
      onSelectVersion={(v: PolicyVersionInfo) => navigate(`/admin/policies/${slug}/versions/${v.version}`)}
      onSetRecommended={(v: PolicyVersionInfo) => setRecommendedMutation.mutate(v)}
      containerFields={containerFields}
      breadcrumbs={breadcrumbs}
      statusBadge={
        !isNew && policy ? (
          <Badge tone={policy.is_active ? 'success' : 'neutral'} size="small">
            {policy.is_active ? 'Активна' : 'Неактивна'}
          </Badge>
        ) : undefined
      }
      renderVersionContent={() => (
        <PolicyVersionCard
          version={selectedVersion || null}
          onCreateVersion={() => navigate(`/admin/policies/${slug}/versions/new`)}
        />
      )}
    />
  );
}

export default PolicyEditorPage;
