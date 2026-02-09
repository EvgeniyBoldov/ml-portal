/**
 * TenantEditorPage - View/Edit/Create tenant with EntityPage
 * 
 * Unified page for all tenant operations:
 * - View: /admin/tenants/:id (readonly)
 * - Edit: /admin/tenants/:id?mode=edit
 * - Create: /admin/tenants/new
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTenant, useModels } from '@shared/api/hooks/useAdmin';
import { tenantApi } from '@shared/api/tenant';
import { permissionsApi } from '@shared/api';
import { qk } from '@shared/api/keys';
import Button from '@shared/ui/Button';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@shared/ui/ContentBlock';
import { RbacRulesEditor, type RbacPermissions } from '@shared/ui/RbacRulesEditor';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import { Tabs, TabPanel } from '@shared/ui/Tabs';
import styles from './TenantEditorPage.module.css';

interface FormData {
  name: string;
  description: string;
  is_active: boolean;
  extra_embed_model: string;
  ocr: boolean;
  layout: boolean;
}

export function TenantEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // Determine mode: create (no id), view (id, no edit param), edit (id + edit param)
  const isCreate = !id;
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const { data: tenantData, isLoading, refetch } = useTenant(id);
  const { data: modelsData } = useModels({ size: 100 });

  const [formData, setFormData] = useState<FormData>({
    name: '',
    description: '',
    is_active: true,
    extra_embed_model: '',
    ocr: false,
    layout: false,
  });
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('general');
  
  // RBAC state
  const queryClient = useQueryClient();
  const [rbacPermissions, setRbacPermissions] = useState<RbacPermissions>({
    instance_permissions: {},
    agent_permissions: {},
  });
  const [editingRbac, setEditingRbac] = useState(false);
  
  // Load tenant's permission set
  const { data: tenantPermissions } = useQuery({
    queryKey: qk.permissions.list({ scope: 'tenant', tenant_id: id }),
    queryFn: () => permissionsApi.list({ scope: 'tenant', tenant_id: id }),
    enabled: !!id && !isCreate,
  });
  
  const tenantPermSet = tenantPermissions?.find((p: any) => p.scope === 'tenant' && p.tenant_id === id);
  
  // Save RBAC mutation
  const saveRbacMutation = useMutation({
    mutationFn: async () => {
      if (tenantPermSet) {
        return permissionsApi.update(tenantPermSet.id, {
          instance_permissions: rbacPermissions.instance_permissions,
          agent_permissions: rbacPermissions.agent_permissions,
        });
      } else {
        return permissionsApi.create({
          scope: 'tenant',
          tenant_id: id!,
          instance_permissions: rbacPermissions.instance_permissions,
          agent_permissions: rbacPermissions.agent_permissions,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.permissions.list({ scope: 'tenant', tenant_id: id }) });
      showSuccess('Права доступа сохранены');
      setEditingRbac(false);
    },
    onError: () => showError('Ошибка сохранения прав доступа'),
  });
  
  const startEditingRbac = () => {
    setRbacPermissions({
      instance_permissions: tenantPermSet?.instance_permissions || {},
      agent_permissions: tenantPermSet?.agent_permissions || {},
    });
    setEditingRbac(true);
  };

  // Get available embedding models
  const models = modelsData?.items || [];
  const textModels = models.filter(
    (m: any) => m.modality === 'text' && (m.state === 'active' || m.state === 'archived')
  );
  const extraModels = textModels.filter((m: any) => !m.global);

  // Field change handler
  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: FormData) => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const basicInfoFields: FieldDefinition[] = [
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'Введите название тенанта',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      placeholder: 'Краткое описание тенанта',
      rows: 3,
    },
  ];

  const statusFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Активен',
      type: 'boolean',
      description: 'Тенант доступен для использования',
    },
  ];

  const embeddingFields: FieldDefinition[] = [
    {
      key: 'extra_embed_model',
      label: 'Дополнительная модель',
      type: 'select',
      options: [
        { value: '', label: 'Не использовать' },
        ...extraModels.map((m: any) => ({
          value: m.model,
          label: `${m.model}${m.state === 'archived' ? ' (архив)' : ''}`,
        })),
      ],
      description: 'Документы будут индексироваться дополнительно этой моделью',
    },
  ];

  const processingFields: FieldDefinition[] = [
    {
      key: 'ocr',
      label: 'OCR',
      type: 'boolean',
      description: 'Распознавание текста на изображениях',
    },
    {
      key: 'layout',
      label: 'Layout Analysis',
      type: 'boolean',
      description: 'Анализ структуры документа',
    },
  ];

  useEffect(() => {
    if (tenantData) {
      setFormData({
        name: tenantData.name || '',
        description: tenantData.description || '',
        is_active: tenantData.is_active ?? true,
        extra_embed_model: (tenantData as any).extra_embed_model || '',
        ocr: tenantData.ocr || false,
        layout: tenantData.layout || false,
      });
    }
  }, [tenantData]);

  const handleSave = async () => {
    if (!formData.name.trim()) {
      showError('Название обязательно');
      return;
    }

    setSaving(true);
    try {
      if (mode === 'edit') {
        await tenantApi.updateTenant(id!, {
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || null,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Тенант обновлён');
        setSearchParams({}); // Switch back to view mode
        refetch();
      } else {
        await tenantApi.createTenant({
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || undefined,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Тенант создан');
        navigate('/admin/tenants');
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (mode === 'edit') {
      // Reset form to original data
      if (tenantData) {
        setFormData({
          name: tenantData.name || '',
          description: tenantData.description || '',
          is_active: tenantData.is_active ?? true,
          extra_embed_model: (tenantData as any).extra_embed_model || '',
          ocr: tenantData.ocr || false,
          layout: tenantData.layout || false,
        });
      }
      setSearchParams({});
    }
  };

  const handleDelete = async () => {
    if (!confirm('Удалить этот тенант?')) return;
    try {
      await tenantApi.deleteTenant(id!);
      showSuccess('Тенант удалён');
      navigate('/admin/tenants');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  return (
    <EntityPage
      mode={mode}
      entityName={tenantData?.name || 'Новый тенант'}
      entityTypeLabel="тенанта"
      backPath="/admin/tenants"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id}
    >
      {!isCreate && id ? (
        <Tabs
          tabs={[
            { id: 'general', label: 'Основное' },
            { id: 'rbac', label: 'RBAC правила' },
          ]}
          activeTab={activeTab}
          onChange={setActiveTab}
        >
          <TabPanel id="general" activeTab={activeTab}>
            <ContentGrid>
              <ContentBlock
                width="2/3"
                title="Основная информация"
                icon="info"
                editable={isEditable}
                fields={basicInfoFields}
                data={formData}
                onChange={handleFieldChange}
              />
              <ContentBlock
                width="1/3"
                title="Статус"
                icon="toggle-left"
                editable={isEditable}
                fields={statusFields}
                data={formData}
                onChange={handleFieldChange}
              />
              <ContentBlock
                width="1/3"
                title="Модели эмбеддинга"
                icon="cpu"
                editable={isEditable}
                fields={embeddingFields}
                data={formData}
                onChange={handleFieldChange}
              />
              <ContentBlock
                width="1/3"
                title="Настройки обработки"
                icon="settings"
                editable={isEditable}
                fields={processingFields}
                data={formData}
                onChange={handleFieldChange}
              />

            </ContentGrid>
          </TabPanel>

          <TabPanel id="rbac" activeTab={activeTab}>
            <RBACRulesTable mode="tenant" levelId={id} />
          </TabPanel>
        </Tabs>
      ) : (
        <ContentGrid>
          <ContentBlock
            width="2/3"
            title="Основная информация"
            icon="info"
            editable={isEditable}
            fields={basicInfoFields}
            data={formData}
            onChange={handleFieldChange}
          />
          <ContentBlock
            width="1/3"
            title="Статус"
            icon="toggle-left"
            editable={isEditable}
            fields={statusFields}
            data={formData}
            onChange={handleFieldChange}
          />
          <ContentBlock
            width="1/3"
            title="Модели эмбеддинга"
            icon="cpu"
            editable={isEditable}
            fields={embeddingFields}
            data={formData}
            onChange={handleFieldChange}
          />
          <ContentBlock
            width="1/3"
            title="Настройки обработки"
            icon="settings"
            editable={isEditable}
            fields={processingFields}
            data={formData}
            onChange={handleFieldChange}
          />
        </ContentGrid>
      )}
    </EntityPage>
  );
}

export default TenantEditorPage;
