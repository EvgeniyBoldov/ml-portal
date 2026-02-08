/**
 * PolicyEditorPage - now shows LIMIT editor (execution constraints)
 * 
 * Old Policy editor becomes Limit editor.
 * Uses EntityTabsPage for unified layout.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { limitsApi, type LimitDetail, type LimitVersionInfo } from '@/shared/api/limits';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityTabsPage, PolicyVersionCard, type FieldDefinition, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui';

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

  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
  });

  const { data: limit, isLoading } = useQuery({
    queryKey: qk.limits.detail(slug!),
    queryFn: () => limitsApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  const activeVersion = limit?.versions?.find(v => v.status === 'active') || limit?.versions?.[0];
  const { data: selectedVersion } = useQuery({
    queryKey: qk.limits.version(slug!, activeVersion?.version ?? 0),
    queryFn: () => limitsApi.getVersion(slug!, activeVersion!.version),
    enabled: !!slug && !!activeVersion,
  });

  useEffect(() => {
    if (limit) {
      setFormData({
        slug: limit.slug,
        name: limit.name,
        description: limit.description || '',
      });
    }
  }, [limit]);

  const createMutation = useMutation({
    mutationFn: (data: any) => limitsApi.create(data),
    onSuccess: (created: any) => {
      queryClient.invalidateQueries({ queryKey: qk.limits.list() });
      showSuccess('Лимит создан');
      navigate(`/admin/limits/${created.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => limitsApi.update(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.limits.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.limits.list() });
      showSuccess('Лимит обновлён');
      setSearchParams({});
    },
    onError: (err: any) => showError(err?.message || 'Ошибка обновления'),
  });

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
        });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/limits');
    } else {
      if (limit) {
        setFormData({
          slug: limit.slug,
          name: limit.name,
          description: limit.description || '',
        });
      }
      setSearchParams({});
    }
  };

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

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
  ];

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Лимиты', href: '/admin/limits' },
    { label: limit?.name || 'Новый лимит' },
  ];

  return (
    <EntityTabsPage
      entityType="policy"
      entityNameLabel="Лимит"
      entityTypeLabel="лимита"
      slug={slug!}
      basePath="/admin/limits"
      listPath="/admin/limits"
      container={limit || null}
      versions={limit?.versions || []}
      isLoading={isLoading}
      formData={formData}
      mode={mode}
      saving={saving}
      onFieldChange={handleFieldChange}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onCreateVersion={() => navigate(`/admin/limits/${slug}/versions/new`)}
      onSelectVersion={(v: LimitVersionInfo) => navigate(`/admin/limits/${slug}/versions/${v.version}`)}
      containerFields={containerFields}
      breadcrumbs={breadcrumbs}
      renderVersionContent={() => (
        <PolicyVersionCard
          version={selectedVersion || null}
          onCreateVersion={() => navigate(`/admin/limits/${slug}/versions/new`)}
        />
      )}
    />
  );
}

export default PolicyEditorPage;
