/**
 * TenantEditorPage - View/Edit/Create tenant with EntityPageV2
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTenant, useModels } from '@shared/api/hooks/useAdmin';
import { tenantApi } from '@shared/api/tenant';
import { qk } from '@shared/api/keys';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { EntityPageV2, Tab, type EntityPageMode } from '@shared/ui/EntityPage/EntityPageV2';
import { ContentBlock, type FieldDefinition } from '@shared/ui/ContentBlock';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
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

  const isNew = !id || id === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const editable = mode === 'edit' || mode === 'create';

  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

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

  const models = modelsData?.items || [];
  const extraModels = models.filter(
    (m: any) => m.modality === 'text' && (m.state === 'active' || m.state === 'archived') && !m.global
  );

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  // ─── Field definitions ───
  const basicInfoFields: FieldDefinition[] = [
    { key: 'name', label: 'Название', type: 'text', required: true, placeholder: 'Введите название тенанта' },
    { key: 'description', label: 'Описание', type: 'textarea', placeholder: 'Краткое описание тенанта', rows: 3 },
  ];

  const statusFields: FieldDefinition[] = [
    { key: 'is_active', label: 'Активен', type: 'boolean', description: 'Тенант доступен для использования' },
  ];

  const embeddingFields: FieldDefinition[] = [
    {
      key: 'extra_embed_model',
      label: 'Дополнительная модель',
      type: 'select',
      options: [
        { value: '', label: 'Не использовать' },
        ...extraModels.map((m: any) => ({ value: m.model, label: `${m.model}${m.state === 'archived' ? ' (архив)' : ''}` })),
      ],
      description: 'Документы будут индексироваться дополнительно этой моделью',
    },
  ];

  const processingFields: FieldDefinition[] = [
    { key: 'ocr', label: 'OCR', type: 'boolean', description: 'Распознавание текста на изображениях' },
    { key: 'layout', label: 'Layout Analysis', type: 'boolean', description: 'Анализ структуры документа' },
  ];

  // ─── Sync form with data ───
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

  // ─── Handlers ───
  const handleSave = async () => {
    if (!formData.name.trim()) { showError('Название обязательно'); return; }
    setSaving(true);
    try {
      if (mode === 'edit') {
        await tenantApi.updateTenant(id!, {
          name: formData.name, description: formData.description,
          is_active: formData.is_active, extra_embed_model: formData.extra_embed_model || null,
          ocr: formData.ocr, layout: formData.layout,
        });
        showSuccess('Тенант обновлён');
        setSearchParams({});
        refetch();
      } else {
        await tenantApi.createTenant({
          name: formData.name, description: formData.description,
          is_active: formData.is_active, extra_embed_model: formData.extra_embed_model || undefined,
          ocr: formData.ocr, layout: formData.layout,
        });
        showSuccess('Тенант создан');
        navigate('/admin/tenants');
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally { setSaving(false); }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (mode === 'edit' && tenantData) {
      setFormData({
        name: tenantData.name || '', description: tenantData.description || '',
        is_active: tenantData.is_active ?? true, extra_embed_model: (tenantData as any).extra_embed_model || '',
        ocr: tenantData.ocr || false, layout: tenantData.layout || false,
      });
      setSearchParams({});
    } else if (isNew) { navigate('/admin/tenants'); }
  };

  const handleDelete = () => setShowDeleteConfirm(true);
  const handleDeleteConfirm = async () => {
    try {
      await tenantApi.deleteTenant(id!);
      showSuccess('Тенант удалён');
      navigate('/admin/tenants');
    } catch (err) { showError(err instanceof Error ? err.message : 'Ошибка удаления'); }
    setShowDeleteConfirm(false);
  };

  // ─── Render ───
  return (
    <>
    <EntityPageV2
      title={tenantData?.name || 'Новый тенант'}
      mode={mode}
      loading={!isNew && isLoading}
      saving={saving}
      breadcrumbs={[
        { label: 'Тенанты', href: '/admin/tenants' },
        { label: tenantData?.name || 'Новый тенант' },
      ]}
      backPath="/admin/tenants"
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id}
    >
      <Tab title="Обзор" layout="grid">
        <ContentBlock title="Основная информация" icon="info" editable={editable} fields={basicInfoFields} data={formData} onChange={handleFieldChange} />
        <ContentBlock title="Статус" icon="toggle-left" editable={editable} fields={statusFields} data={formData} onChange={handleFieldChange} />
        <ContentBlock title="Модели эмбеддинга" icon="cpu" editable={editable} fields={embeddingFields} data={formData} onChange={handleFieldChange} />
        <ContentBlock title="Настройки обработки" icon="settings" editable={editable} fields={processingFields} data={formData} onChange={handleFieldChange} />
      </Tab>

      {!isNew && (
        <Tab title="RBAC правила" layout="full">
          <RBACRulesTable mode="tenant" ownerId={id} />
        </Tab>
      )}
    </EntityPageV2>

    <ConfirmDialog
      open={showDeleteConfirm}
      title="Удалить тенант?"
      message="Вы уверены? Это действие нельзя отменить."
      confirmLabel="Удалить"
      cancelLabel="Отмена"
      variant="danger"
      onConfirm={handleDeleteConfirm}
      onCancel={() => setShowDeleteConfirm(false)}
    />
    </>
  );
}

export default TenantEditorPage;
