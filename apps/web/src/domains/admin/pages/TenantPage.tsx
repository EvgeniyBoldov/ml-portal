/**
 * TenantPage - Admin page for managing Tenants
 * 
 * Uses Block + GridLayout system for structured layout.
 * Data flows: API types → formData state → Block fields.
 * No mappers, no intermediate interfaces.
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTenant, useModels } from '@shared/api/hooks/useAdmin';
import { tenantApi } from '@shared/api/tenant';
import { agentsApi, type Agent } from '@shared/api/agents';
import { qk } from '@shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Button, ConfirmDialog } from '@/shared/ui';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import type { Tenant, TenantCreate, TenantUpdate } from '@shared/api/tenant';

/* ─── Field configs ─── */

const INFO_FIELDS: FieldConfig[] = [
  {
    key: 'name',
    type: 'text',
    label: 'Название',
    required: true,
    placeholder: 'Введите название тенанта',
    description: 'Уникальное название тенанта',
  },
  {
    key: 'description',
    type: 'textarea',
    label: 'Описание',
    placeholder: 'Краткое описание тенанта',
    rows: 3,
  },
];

const STATUS_FIELDS: FieldConfig[] = [
  {
    key: 'is_active',
    type: 'boolean',
    label: 'Активен',
    description: 'Тенант доступен для использования',
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

const PROCESSING_FIELDS: FieldConfig[] = [
  {
    key: 'ocr',
    type: 'boolean',
    label: 'OCR',
    description: 'Распознавание текста на изображениях',
  },
  {
    key: 'layout',
    type: 'boolean',
    label: 'Layout Analysis',
    description: 'Анализ структуры документа',
  },
];

const AGENT_FIELDS: FieldConfig[] = [
  {
    key: 'default_agent_slug',
    type: 'select',
    label: 'Агент по умолчанию',
    description: 'Агент, используемый при отсутствии явного выбора',
    options: [],
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
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

  const [formData, setFormData] = useState<Partial<TenantCreate>>({
    name: '',
    description: '',
    is_active: true,
    extra_embed_model: '',
    ocr: false,
    layout: false,
  });
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // ─── Queries ───
  const { data: tenant, isLoading, refetch } = useTenant(id);
  const { data: modelsData } = useModels({ size: 100 });
  const { data: agentsList } = useQuery({
    queryKey: qk.agents.list({}),
    queryFn: () => agentsApi.list(),
  });

  // ─── Sync form ←→ API ───
  useEffect(() => {
    if (tenant) {
      setFormData({
        name: tenant.name || '',
        description: tenant.description || '',
        is_active: tenant.is_active,
        extra_embed_model: tenant.extra_embed_model || '',
        ocr: tenant.ocr || false,
        layout: tenant.layout || false,
        default_agent_slug: tenant.default_agent_slug || '',
      });
    }
  }, [tenant]);

  // ─── Mutations ───
  const createMutation = useMutation({
    mutationFn: (data: TenantCreate) => tenantApi.createTenant(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
      showSuccess('Тенант создан');
      navigate('/admin/tenants');
    },
    onError: (err: Error) => showError(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (data: TenantUpdate) => tenantApi.updateTenant(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants.detail(id!) });
      showSuccess('Тенант обновлён');
      setSearchParams({});
      refetch();
    },
    onError: (err: Error) => showError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => tenantApi.deleteTenant(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.admin.tenants.all() });
      showSuccess('Тенант удалён');
      navigate('/admin/tenants');
    },
    onError: (err: Error) => showError(err.message),
  });

  // ─── Handlers ───
  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        await createMutation.mutateAsync(formData as TenantCreate);
      } else {
        await updateMutation.mutateAsync(formData as TenantUpdate);
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
          extra_embed_model: tenant.extra_embed_model || '',
          ocr: tenant.ocr || false,
          layout: tenant.layout || false,
          default_agent_slug: tenant.default_agent_slug || '',
        });
      }
      setSearchParams({});
    }
  };

  const handleDelete = () => setShowDeleteConfirm(true);

  const handleDeleteConfirm = async () => {
    try {
      await deleteMutation.mutateAsync();
      setShowDeleteConfirm(false);
    } finally {
      setSaving(false);
    }
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Тенанты', href: '/admin/tenants' },
    { label: tenant?.name || 'Новый тенант' },
  ];

  // ─── Derived data for blocks ───
  const infoData = mode === 'edit' ? formData : {
    name: tenant?.name || '',
    description: tenant?.description || '',
  };

  const statusData = mode === 'edit' ? formData : {
    is_active: tenant?.is_active || false,
  };

  const embeddingData = mode === 'edit' ? formData : {
    extra_embed_model: tenant?.extra_embed_model || '',
  };

  const processingData = mode === 'edit' ? formData : {
    ocr: tenant?.ocr || false,
    layout: tenant?.layout || false,
  };

  const agentData = mode === 'edit' ? formData : {
    default_agent_slug: tenant?.default_agent_slug || '',
  };

  const agentOptions = [
    { value: '', label: '— Не выбран (fallback: rag-search) —' },
    ...(agentsList ?? []).map((a: Agent) => ({
      value: a.slug,
      label: `${a.name} (${a.slug})`,
    })),
  ];

  const metaData = {
    id: tenant?.id || '',
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

  // ─── Create mode ───
  if (isNew) {
    return (
      <EntityPageV2
        title="Новый тенант"
        mode={mode}
        saving={saving}
        breadcrumbs={breadcrumbs}
        backPath="/admin/tenants"
        onSave={handleSave}
        onCancel={handleCancel}
      >
        <Tab title="Создание" layout="single">
          {/* Row 1: Info (full) */}
          <Block
            title="Основная информация"
            icon="building"
            iconVariant="info"
            width="full"
            fields={INFO_FIELDS}
            data={formData}
            editable={true}
            onChange={handleFieldChange}
          />

          {/* Row 2: Status (1/2) + Embedding (1/2) */}
          <Block
            title="Статус"
            icon="toggle-left"
            iconVariant="success"
            width="1/2"
            fields={STATUS_FIELDS}
            data={formData}
            editable={true}
            onChange={handleFieldChange}
          />

          <Block
            title="Модель эмбеддинга"
            icon="cpu"
            iconVariant="primary"
            width="1/2"
            fields={[{ ...EMBEDDING_FIELDS[0], options: embeddingOptions }]}
            data={embeddingData}
            editable={true}
            onChange={handleFieldChange}
          />

          {/* Row 3: Processing (1/2) + Agent (1/2) */}
          <Block
            title="Настройки обработки"
            icon="settings"
            iconVariant="warning"
            width="1/2"
            fields={PROCESSING_FIELDS}
            data={formData}
            editable={true}
            onChange={handleFieldChange}
          />

          <Block
            title="Агент"
            icon="bot"
            iconVariant="primary"
            width="1/2"
            fields={[{ ...AGENT_FIELDS[0], options: agentOptions }]}
            data={formData}
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
        title={tenant?.name || 'Тенант'}
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
              <Button key="edit" onClick={handleEdit}>Редактировать</Button>,
            ] : mode === 'edit' ? [
              <Button key="save" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel}>Отмена</Button>,
            ] : []
          }
        >
          {/* Row 1: Info (full) */}
          <Block
            title="Основная информация"
            icon="building"
            iconVariant="info"
            width="full"
            fields={INFO_FIELDS}
            data={infoData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          {/* Row 2: Status (1/2) + Embedding (1/2) */}
          <Block
            title="Статус"
            icon="toggle-left"
            iconVariant="success"
            width="1/2"
            fields={STATUS_FIELDS}
            data={statusData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Модель эмбеддинга"
            icon="cpu"
            iconVariant="primary"
            width="1/2"
            fields={[{ ...EMBEDDING_FIELDS[0], options: embeddingOptions }]}
            data={embeddingData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          {/* Row 3: Processing (1/3) + Agent (1/3) + Meta (1/3) */}
          <Block
            title="Настройки обработки"
            icon="settings"
            iconVariant="warning"
            width="1/3"
            fields={PROCESSING_FIELDS}
            data={processingData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Агент по умолчанию"
            icon="bot"
            iconVariant="primary"
            width="1/3"
            fields={[{ ...AGENT_FIELDS[0], options: agentOptions }]}
            data={agentData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Метаданные"
            icon="database"
            iconVariant="info"
            width="1/3"
            fields={META_FIELDS}
            data={metaData}
          />
        </Tab>

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

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить тенант?"
        message={
          <div>
            <p>Вы уверены, что хотите удалить тенант <strong>{tenant?.name}</strong>?</p>
            <p>Это действие нельзя отменить.</p>
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

export default TenantPage;
