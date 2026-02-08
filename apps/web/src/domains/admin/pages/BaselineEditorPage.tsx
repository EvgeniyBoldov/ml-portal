/**
 * BaselineEditorPage - now shows POLICY editor (text-based behavioral rules)
 * 
 * Old Baseline editor becomes Policy editor.
 * Uses EntityTabsPage for unified layout.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyDetail, type PolicyVersionInfo } from '@/shared/api/policies';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityTabsPage, PromptVersionCard, type FieldDefinition, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui';

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

  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
  });

  const { data: policy, isLoading } = useQuery({
    queryKey: qk.policies.detail(slug!),
    queryFn: () => policiesApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  const activeVersion = policy?.versions?.find(v => v.status === 'active') || policy?.versions?.[0];
  const { data: selectedVersion } = useQuery({
    queryKey: qk.policies.version(slug!, activeVersion?.version ?? 0),
    queryFn: () => policiesApi.getVersion(slug!, activeVersion!.version),
    enabled: !!slug && !!activeVersion,
  });

  useEffect(() => {
    if (policy) {
      setFormData({
        slug: policy.slug,
        name: policy.name,
        description: policy.description || '',
      });
    }
  }, [policy]);

  const createMutation = useMutation({
    mutationFn: (data: any) => policiesApi.create(data),
    onSuccess: (created: any) => {
      queryClient.invalidateQueries({ queryKey: qk.policies.list() });
      showSuccess('Политика создана');
      navigate(`/admin/policies/${created.slug}`);
    },
    onError: (err: any) => showError(err?.message || 'Ошибка создания'),
  });

  const updateMutation = useMutation({
    mutationFn: (data: any) => policiesApi.update(slug!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.list() });
      showSuccess('Политика обновлена');
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
      navigate('/admin/policies');
    } else {
      if (policy) {
        setFormData({
          slug: policy.slug,
          name: policy.name,
          description: policy.description || '',
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
      placeholder: 'Правила поведения агента...',
      rows: 2,
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
      containerFields={containerFields}
      breadcrumbs={breadcrumbs}
      renderVersionContent={() => (
        <PromptVersionCard
          version={selectedVersion ? { ...selectedVersion, template: selectedVersion.policy_text } : null}
          onCreateVersion={() => navigate(`/admin/policies/${slug}/versions/new`)}
        />
      )}
    />
  );
}

export default BaselineEditorPage;
