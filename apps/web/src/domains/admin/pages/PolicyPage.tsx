/**
 * PolicyEditorPageV2 - Policy editor with new EntityPageV2 + Tab architecture
 * 
 * Declarative tabs with existing shared blocks inside.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { policiesApi, type PolicyDetail, type PolicyVersionInfo } from '@/shared/api/policies';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import Button from '@/shared/ui/Button';
import { EntityInfoBlock } from '@/shared/ui/EntityInfoBlock';
import { ShortVersionBlock } from '@/shared/ui/ShortVersionBlock';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import { PolicyVersionContent } from '@/domains/policies/components/PolicyVersionContent';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import { useEntityFields } from '@/shared/hooks/useEntityFields';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui';

export function PolicyPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !slug || slug === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  
  // Dynamic fields based on mode
  const containerFields = useEntityFields(mode);

  // Form state
  const [formData, setFormData] = useState({
    slug: '',
    name: '',
    description: '',
  });

  // Load policy data
  const { data: policy, isLoading } = useQuery({
    queryKey: qk.policies.detail(slug!),
    queryFn: () => policiesApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  const versions = policy?.versions || [];
  const currentVersion = policy?.current_version;

  // Sync form with entity data
  useEffect(() => {
    if (policy) {
      setFormData({
        slug: policy.slug,
        name: policy.name,
        description: policy.description || '',
      });
    } else if (isNew) {
      setFormData({ slug: '', name: '', description: '' });
    }
  }, [policy, isNew]);

  // Mutations
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

  const deleteMutation = useMutation({
    mutationFn: () => policiesApi.delete(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.policies.list() });
      showSuccess('Политика удалена');
      navigate('/admin/policies');
    },
    onError: (err: any) => showError(err?.message || 'Ошибка удаления'),
  });

  // Handlers
  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: any) => ({ ...prev, [key]: value }));
  };

  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
    await deleteMutation.mutateAsync();
  };

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

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Политики', href: '/admin/policies' },
    { label: policy?.name || 'Новая политика' },
  ];

  // Create mode — single tab, single column
  if (isNew) {
    return (
      <EntityPageV2
        title="Новая политика"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/policies"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="single">
          <EntityInfoBlock
            entity={formData}
            entityType="policy"
            editable={true}
            fields={containerFields}
            onFieldChange={handleFieldChange}
          />
        </Tab>
      </EntityPageV2>
    );
  }

  // View/Edit mode — two tabs
  return (
    <>
    <EntityPageV2
      title={policy?.name || 'Политика'}
      mode={mode}
      loading={isLoading}
      saving={saving}
      breadcrumbs={breadcrumbs}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
    >
      <Tab 
        title="Обзор" 
        layout="grid" 
        id="overview"
        actions={
          mode === 'view' ? [
            <Button key="edit" onClick={handleEdit}>
              Редактировать
            </Button>,
            <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              Удалить
            </Button>,
          ] : mode === 'edit' ? [
            <Button key="save" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : []
        }
      >
        <EntityInfoBlock
          entity={mode === 'edit' ? formData : (policy || formData)}
          entityType="policy"
          editable={mode === 'edit'}
          fields={containerFields}
          onFieldChange={handleFieldChange}
        />
        {currentVersion ? (
          <ShortVersionBlock
            title="Основная версия"
            entityType="policy"
            version={currentVersion}
          >
            <PolicyVersionContent version={currentVersion} />
          </ShortVersionBlock>
        ) : (
          <ShortVersionBlock
            title="Основная версия"
            version={{
              version: 0,
              created_at: new Date().toISOString(),
            }}
          >
            <div>Нет основной версии</div>
          </ShortVersionBlock>
        )}
      </Tab>

      <Tab
        title="Версии"
        layout="full"
        id="versions"
        badge={versions.length}
        actions={[
          <Button key="create" onClick={() => navigate(`/admin/policies/${slug}/versions/new`)}>
            Создать версию
          </Button>,
        ]}
      >
        <VersionsBlock
          entityType="policy"
          versions={versions}
          selectedVersion={currentVersion}
          onSelectVersion={(version) => navigate(`/admin/policies/${slug}/versions/${version.version}`)}
        />
      </Tab>
    </EntityPageV2>

    <ConfirmDialog
      open={showDeleteConfirm}
      title="Удалить политику?"
      message={
        <div>
          <p>Вы уверены, что хотите удалить политику <strong>{policy?.name}</strong>?</p>
          <p>Это действие удалит все версии. Отменить его невозможно.</p>
        </div>
      }
      confirmLabel="Удалить"
      cancelLabel="Отмена"
      variant="danger"
      onConfirm={handleDeleteConfirm}
      onCancel={() => setShowDeleteConfirm(false)}
    />
    </>
  );
}

export default PolicyPage;
