/**
 * TenantPage - Admin page for managing Tenants
 * 
 * Uses Block + GridLayout system for structured layout.
 * Data flows: API types → formData state → Block fields.
 * No mappers, no intermediate interfaces.
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useTenant, useModels, useCreateTenant, useUpdateTenant, useUsers } from '@shared/api/hooks/useAdmin';
import { qk } from '@shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui/EntityPage';
import { buildEntityCrudActions } from '@/shared/ui/EntityPage/entityCrudActions';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { LifecycleDeleteDialog } from '@/shared/ui';
import LifecycleRestoreDialog from '@/shared/ui/LifecycleRestoreDialog';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable/RBACRulesTable';
import type { Tenant, TenantCreate, TenantUpdate } from '@shared/api/tenant';
import { CredentialsPanel } from '@/shared/ui';
import MultiSelectTagPicker from '@/shared/ui/MultiSelectTagPicker/MultiSelectTagPicker';

type TenantFormData = Partial<TenantCreate & { is_default?: boolean; tenant_admin_user_ids?: string[] }>;

/* ─── Field configs ─── */

const INFO_FIELDS: FieldConfig[] = [
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'Введите название рабочей группы',
    description: 'Уникальное название рабочей группы',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Краткое описание рабочей группы',
    rows: 3,
  },
];

const EMBEDDING_FIELDS: FieldConfig[] = [
  {
    key: 'extra_embed_model',
    type: 'select',
    label: 'Модель эмбеддинга',
    description: 'Основная модель для индексации документов',
    options: [],
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
  { key: 'is_default', type: 'boolean', label: 'Рабочая группа по умолчанию', editable: false },
  { key: 'created_at', type: 'date', label: 'Создан', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлен', editable: false },
];

/* ─── Component ─── */

export function TenantPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !id || id === 'new';
  const modeParam = searchParams.get('mode');
  const mode: EntityPageMode = isNew ? 'create' : (modeParam as EntityPageMode) || 'view';

  const [formData, setFormData] = useState<TenantFormData>({
    name: '',
    description: '',
    is_active: true,
    is_default: false,
    extra_embed_model: '',
    tenant_admin_user_ids: [],
  });
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);

  // ─── Queries ───
  const { data: tenant, isLoading, refetch } = useTenant(id);
  const { data: modelsData } = useModels({ size: 100 });
  const usersQuery = useUsers({ limit: 100, include_deprecated: false });
  useEffect(() => {
    if (usersQuery.hasNextPage) void usersQuery.fetchNextPage();
  }, [usersQuery.hasNextPage, usersQuery.fetchNextPage]);
  const tenantUsers = (usersQuery.data?.pages.flatMap(page => page.users) ?? []).filter(user => user.tenant_id === id);

  // ─── Sync form ←→ API ───
  useEffect(() => {
    if (tenant) {
      setFormData({
        name: tenant.name || '',
        description: tenant.description || '',
        is_active: tenant.is_active,
        is_default: Boolean(tenant.is_default),
        extra_embed_model: tenant.extra_embed_model || '',
        tenant_admin_user_ids: tenant.tenant_admin_user_ids ?? [],
      });
    }
  }, [tenant]);

  // ─── Mutations ───
  const createMutation = useCreateTenant();
  const updateMutation = useUpdateTenant();

  // ─── Handlers ───
  const handleFieldChange = (key: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [key]: value }) as TenantFormData);
  };

  const handleSave = async () => {
    if (!formData.name?.trim()) {
      showError('Название рабочей группы обязательно');
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        await createMutation.mutateAsync({
          name: formData.name?.trim() ?? '',
          description: formData.description?.trim() || null,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || null,
        });
        showSuccess('Рабочая группа создана');
        navigate('/admin/tenants');
      } else {
        await updateMutation.mutateAsync({
          id: id!,
          data: {
            name: formData.name?.trim(),
            description: formData.description?.trim() || null,
            is_active: formData.is_active,
            is_default: formData.is_default,
            extra_embed_model: formData.extra_embed_model || null,
            tenant_admin_user_ids: formData.tenant_admin_user_ids ?? [],
          },
        });
        showSuccess('Рабочая группа обновлена');
        setSearchParams({});
        refetch();
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/tenants');
    } else {
      if (tenant) {
        setFormData({
          name: tenant.name || '',
          description: tenant.description || '',
          is_active: tenant.is_active,
          is_default: Boolean(tenant.is_default),
          extra_embed_model: tenant.extra_embed_model || '',
          tenant_admin_user_ids: tenant.tenant_admin_user_ids ?? [],
        });
      }
      setSearchParams({});
    }
  };

  const handleDelete = () => setShowDeleteConfirm(true);

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Рабочие группы', href: '/admin/tenants' },
    { label: tenant?.name || 'Новая рабочая группа' },
  ];

  // ─── Derived data for blocks ───
  const infoData = mode === 'edit' ? formData : {
    name: tenant?.name || '',
    description: tenant?.description || '',
    is_default: Boolean(tenant?.is_default),
    tenant_admin_user_ids: tenant?.tenant_admin_user_ids ?? [],
  };

  const embeddingData = mode === 'edit' ? formData : {
    extra_embed_model: tenant?.extra_embed_model || '',
  };

  const metaData = {
    id: tenant?.id || '',
    is_default: Boolean(tenant?.is_default),
    created_at: tenant?.created_at || '',
    updated_at: tenant?.updated_at || '',
  };

  // Options for embedding models
  const models = modelsData?.items ?? [];
  const embeddingModels = models.filter(
    (m) => m.type === 'embedding' && (m.status === 'available' || m.status === 'deprecated')
  );
  
  const embeddingOptions = [
    { value: '', label: '— Не выбрана —' },
    ...embeddingModels.map((m) => ({
      value: m.alias,
      label: `${m.name} (${m.alias})${m.status === 'deprecated' ? ' (устарела)' : ''}`,
    })),
  ];
  const infoFieldsWithStatus: FieldConfig[] = [
    ...INFO_FIELDS,
    {
      key: 'is_active',
      type: 'boolean',
      label: 'Активен',
      description: 'Рабочая группа доступна для использования',
    },
    {
      key: 'is_default',
      type: 'boolean',
      label: 'Рабочая группа по умолчанию',
      description: 'Рабочая группа платформы по умолчанию',
    },
  ];
  const tenantAdminField: FieldConfig = {
    key: 'tenant_admin_user_ids',
    type: 'custom',
    label: 'Администраторы рабочей группы',
    description: 'Участники, которые смогут управлять редакторами и credentials рабочей группы.',
    render: (value, editable, onChange) => (
      <MultiSelectTagPicker
        label="Администраторы рабочей группы"
        options={tenantUsers.map(user => ({
          value: user.id,
          label: user.full_name || user.login,
        }))}
        value={Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []}
        hideLabel
        readOnly={!editable}
        emptyMessage="Администраторы не назначены"
        placeholder="Найти участника рабочей группы"
        disabled={saving}
        onChange={onChange}
      />
    ),
  };
  const infoFieldsCreate: FieldConfig[] = infoFieldsWithStatus.filter((field) => field.key !== 'is_default');
  const embeddingFieldsFull: FieldConfig[] = [{ ...EMBEDDING_FIELDS[0], options: embeddingOptions }];

  // ─── Create mode ───
  if (isNew) {
    return (
      <EntityPageV2
        title="Новая рабочая группа"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/tenants"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="single">
          <Block
            title="Основная информация"
            icon="building"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsCreate}
            data={formData}
            editable={true}
            onChange={handleFieldChange}
          />

          <Block
            title="Обработка"
            icon="cpu"
            iconVariant="primary"
            width="1/2"
            fields={embeddingFieldsFull}
            data={embeddingData}
            editable={true}
            onChange={handleFieldChange}
          />
        </Tab>
      </EntityPageV2>
    );
  }

  // ─── View / Edit mode ───
  return (
    <>
      <EntityPageV2
        title={tenant?.name || 'Рабочая группа'}
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
          actions={buildEntityCrudActions({
            mode,
            saving,
            tone: 'default',
            labels: {
              edit: 'Изменить',
              delete: 'Удалить',
            },
            lifecycleStatus: tenant?.lifecycle_status,
            onEdit: handleEdit,
            onSave: handleSave,
            onCancel: handleCancel,
            onDelete: handleDelete,
            onRestore: () => setShowRestoreConfirm(true),
            restorePending: showRestoreConfirm,
          })}
        >
          <Block
            title="Основная информация"
            icon="building"
            iconVariant="info"
            width="1/2"
            fields={infoFieldsWithStatus}
            data={{ ...infoData, is_active: mode === 'edit' ? formData.is_active : (tenant?.is_active || false) }}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Управление доступом"
            icon="users"
            iconVariant="info"
            width="1/2"
            fields={[tenantAdminField]}
            data={mode === 'edit' ? formData : { tenant_admin_user_ids: tenant?.tenant_admin_user_ids ?? [] }}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Обработка"
            icon="cpu"
            iconVariant="primary"
            width="1/2"
            fields={embeddingFieldsFull}
            data={embeddingData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Метаданные"
            icon="database"
            iconVariant="info"
            width="full"
            fields={META_FIELDS}
            data={metaData}
          />
        </Tab>

        {!isNew && (
        <Tab title="Credentials" layout="full" id="credentials">
          <CredentialsPanel mode="readonly-owner" ownerTenantId={id} />
        </Tab>
        )}

        {!isNew && (
        <Tab 
          title="RBAC правила" 
          layout="full"
          id="rbac"
        >
            <RBACRulesTable mode="tenant" ownerId={id} />
        </Tab>
        )}
      </EntityPageV2>

      <LifecycleDeleteDialog
        open={showDeleteConfirm}
        kind="tenant"
        entityId={id || ''}
        entityLabel={tenant?.name || 'Рабочая группа'}
        onCancel={() => setShowDeleteConfirm(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
          queryClient.invalidateQueries({ queryKey: qk.admin.tenants.detail(id || '') });
          showSuccess('Операция удаления выполнена');
          setShowDeleteConfirm(false);
          navigate('/admin/tenants');
        }}
      />

      <LifecycleRestoreDialog
        open={showRestoreConfirm}
        kind="tenant"
        entityId={id || ''}
        entityLabel={tenant?.name || 'Рабочая группа'}
        onCancel={() => setShowRestoreConfirm(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
          queryClient.invalidateQueries({ queryKey: qk.admin.tenants.detail(id || '') });
          showSuccess('Рабочая группа восстановлена');
          setShowRestoreConfirm(false);
        }}
      />
    </>
  );
}

export default TenantPage;
