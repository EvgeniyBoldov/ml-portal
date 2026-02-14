/**
 * LimitEditorPage - Limit editor with EntityPageV2 + Tab architecture
 * 
 * Declarative tabs with existing shared blocks inside.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { limitsApi, type LimitDetail, type LimitVersionInfo } from '@/shared/api/limits';
import { qk } from '@/shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import Button from '@/shared/ui/Button';
import { EntityInfoBlock } from '@/shared/ui/EntityInfoBlock';
import { ShortVersionBlock } from '@/shared/ui/ShortVersionBlock';
import { VersionsBlock } from '@/shared/ui/VersionsBlock';
import { LimitVersionContent } from '@/domains/limits/components/LimitVersionContent';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import { useEntityFields } from '@/shared/hooks/useEntityFields';
import { EntityPageV2, Tab, type EntityPageMode, type BreadcrumbItem } from '@/shared/ui/EntityPage/EntityPageV2';

export function LimitPage() {
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

  // Load limit data
  const { data: limit, isLoading } = useQuery({
    queryKey: qk.limits.detail(slug!),
    queryFn: () => limitsApi.get(slug!),
    enabled: !!slug && !isNew,
  });

  const versions = (limit as any)?.versions || [];
  const currentVersion = (limit as any)?.current_version || (limit as any)?.recommended_version;

  // Sync form with entity data
  useEffect(() => {
    if (limit) {
      setFormData({
        slug: limit.slug,
        name: limit.name,
        description: limit.description || '',
      });
    } else if (isNew) {
      setFormData({ slug: '', name: '', description: '' });
    }
  }, [limit, isNew]);

  // Mutations
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

  const deleteMutation = useMutation({
    mutationFn: () => limitsApi.delete(slug!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.limits.list() });
      showSuccess('Лимит удалён');
      navigate('/admin/limits');
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

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Лимиты', href: '/admin/limits' },
    { label: limit?.name || 'Новый лимит' },
  ];

  // Create mode — single tab, single column
  if (isNew) {
    return (
      <EntityPageV2
        title="Новый лимит"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/limits"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="single">
          <EntityInfoBlock
            entity={formData}
            entityType="limit"
            editable={mode === 'create'}
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
        title={limit?.name || 'Лимит'}
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
          entity={mode === 'edit' ? formData : (limit || formData)}
          entityType="limit"
          editable={mode === 'edit'}
          fields={containerFields}
          onFieldChange={handleFieldChange}
        />
        {currentVersion ? (
          <ShortVersionBlock
            title="Основная версия"
            entityType="limit"
            version={currentVersion}
          >
            <LimitVersionContent version={currentVersion} />
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
          <Button key="create-version" variant="primary" onClick={() => navigate(`/admin/limits/${slug}/versions/new`)}>
            Создать версию
          </Button>,
        ]}
      >
        <VersionsBlock
          entityType="limit"
          versions={versions}
          onSelectVersion={(version) => navigate(`/admin/limits/${slug}/versions/${version.version}`)}
          recommendedVersionId={currentVersion?.id}
        />
      </Tab>
    </EntityPageV2>
    
    <ConfirmDialog
      open={showDeleteConfirm}
      title="Удалить лимит?"
      message={
        <div>
          <p>Вы уверены, что хотите удалить лимит <strong>{limit?.name}</strong>?</p>
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

export default LimitPage;
