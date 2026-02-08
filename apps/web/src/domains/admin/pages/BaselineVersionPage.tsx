/**
 * BaselineVersionPage - now shows POLICY version editor (text-based rules)
 * 
 * Old Baseline version page becomes Policy version page.
 * template → policy_text
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyVersion, type PolicyVersionCreate } from '@/shared/api/policies';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPage, ContentBlock, Textarea, Badge, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';
import { useVersionActions } from '@/shared/hooks/useVersionActions';

export function BaselineVersionPage() {
  const { slug, version: versionParam } = useParams<{ slug: string; version: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isCreate = !versionParam;
  const versionNumber = isCreate ? 0 : parseInt(versionParam, 10);
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const [formData, setFormData] = useState({ policy_text: '', notes: '' });
  const [saving, setSaving] = useState(false);

  const { data: policy } = useQuery({
    queryKey: qk.policies.detail(slug!),
    queryFn: () => policiesApi.get(slug!),
    enabled: !!slug,
  });

  const { data: existingVersion, isLoading } = useQuery({
    queryKey: qk.policies.version(slug!, versionNumber),
    queryFn: () => policiesApi.getVersion(slug!, versionNumber),
    enabled: !isCreate && !!slug && versionNumber > 0,
  });

  useEffect(() => {
    if (isCreate) {
      setFormData({ policy_text: '', notes: '' });
    } else if (existingVersion) {
      setFormData({
        policy_text: existingVersion.policy_text,
        notes: existingVersion.notes || '',
      });
    }
  }, [existingVersion, isCreate]);

  const createMutation = useMutation({
    mutationFn: (data: PolicyVersionCreate) => policiesApi.createVersion(slug!, data),
    onSuccess: (created: PolicyVersion) => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия создана');
      navigate(`/admin/policies/${slug}/versions/${created.version}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: PolicyVersionCreate) => policiesApi.updateVersion(slug!, versionNumber, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.version(slug!, versionNumber) });
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия обновлена');
      setSearchParams({});
    },
    onError: (err: Error) => showError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: () => policiesApi.activateVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.version(slug!, versionNumber) });
      showSuccess('Версия активирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => policiesApi.deactivateVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      queryClient.invalidateQueries({ queryKey: qk.policies.version(slug!, versionNumber) });
      showSuccess('Версия деактивирована');
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => policiesApi.deleteVersion(slug!, versionNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.detail(slug!) });
      showSuccess('Версия удалена');
      navigate(`/admin/policies/${slug}`);
    },
    onError: (err: Error) => showError(err.message),
  });

  const handleSave = async () => {
    if (!formData.policy_text.trim()) {
      showError('Текст политики не может быть пустым');
      return;
    }
    setSaving(true);
    try {
      const data: PolicyVersionCreate = {
        policy_text: formData.policy_text,
        notes: formData.notes || undefined,
      };
      if (isCreate) {
        if (policy?.current_version) {
          data.parent_version_id = policy.current_version.id;
        }
        await createMutation.mutateAsync(data);
      } else {
        await updateMutation.mutateAsync(data);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isCreate) {
      navigate(`/admin/policies/${slug}`);
    } else {
      if (existingVersion) {
        setFormData({
          policy_text: existingVersion.policy_text,
          notes: existingVersion.notes || '',
        });
      }
      setSearchParams({});
    }
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Политики', href: '/admin/policies' },
    { label: policy?.name || slug || '', href: `/admin/policies/${slug}` },
    { label: isCreate ? 'Новая версия' : `Версия ${versionNumber}` },
  ];

  const isCurrent = !!(policy?.current_version_id && existingVersion?.id && policy.current_version_id === existingVersion.id);

  const actionButtons = useVersionActions({
    status: existingVersion?.status,
    isRecommended: isCurrent,
    isCreate,
    callbacks: {
      onEdit: () => setSearchParams({ mode: 'edit' }),
      onActivate: () => activateMutation.mutate(),
      onDeactivate: () => deactivateMutation.mutate(),
    },
    loading: {
      activate: activateMutation.isPending,
      deactivate: deactivateMutation.isPending,
    },
  });

  return (
    <EntityPage
      mode={mode}
      entityName={isCreate ? 'Новая версия' : `Версия ${versionNumber}`}
      entityTypeLabel="версии"
      backPath={`/admin/policies/${slug}`}
      breadcrumbs={breadcrumbs}
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      actionButtons={actionButtons}
    >
      <ContentBlock
        title="Текст политики"
        icon="file-text"
        headerActions={
          !isCreate && existingVersion?.status ? (
            <Badge tone={existingVersion.status === 'active' ? 'success' : existingVersion.status === 'draft' ? 'warn' : 'neutral'} size="small">
              {existingVersion.status === 'active' ? 'Активна' : existingVersion.status === 'draft' ? 'Черновик' : 'Архив'}
            </Badge>
          ) : undefined
        }
      >
          {isEditable ? (
            <Textarea
              value={formData.policy_text}
              onChange={(e) => setFormData(prev => ({ ...prev, policy_text: e.target.value }))}
              placeholder="Введите правила и ограничения для агента..."
              rows={20}
              style={{ fontFamily: 'monospace' }}
            />
          ) : (
            <pre style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              lineHeight: '1.5',
            }}>
              {existingVersion?.policy_text || 'Нет текста политики'}
            </pre>
          )}
      </ContentBlock>

      <ContentBlock title="Заметки" icon="file-text">
        {isEditable ? (
          <Textarea
            value={formData.notes}
            onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
            placeholder="Описание изменений..."
            rows={4}
            style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}
          />
        ) : (
          <pre style={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            lineHeight: '1.5',
          }}>
            {formData.notes || 'Нет заметок'}
          </pre>
        )}
      </ContentBlock>
    </EntityPage>
  );
}

export default BaselineVersionPage;
