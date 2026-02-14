/**
 * CreateCollectionPage - Create a new collection with EntityPageV2 + Tab architecture
 * 
 * Declarative tabs with existing shared blocks inside.
 */
import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { ContentBlock, Button, type BreadcrumbItem, type FieldDefinition } from '@/shared/ui';
import FieldEditor from '@shared/ui/FieldEditor';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { collectionsApi, CollectionField, SearchMode } from '@shared/api/collections';
import { adminApi } from '@shared/api/admin';
import { EntityPageV2, Tab } from '@/shared/ui/EntityPage/EntityPageV2';

interface FieldFormData extends CollectionField {
  id: string;
}

function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

export function CreateCollectionPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const { data: tenantsData, isLoading: tenantsLoading } = useQuery({
    queryKey: ['admin', 'tenants'],
    queryFn: () => adminApi.getTenants(),
  });

  const tenants = tenantsData?.items ?? [];

  const [formData, setFormData] = useState({
    tenant_id: '',
    slug: '',
    name: '',
    description: '',
  });

  const tenantOptions = useMemo(() =>
    tenants.map(t => ({ value: t.id, label: t.name })),
    [tenants],
  );

  const mainFields: FieldDefinition[] = [
    {
      key: 'tenant_id',
      label: 'Тенант',
      type: 'select',
      required: true,
      options: tenantOptions,
    },
    {
      key: 'slug',
      label: 'Slug',
      type: 'code',
      required: true,
      placeholder: 'tickets',
    },
    {
      key: 'name',
      label: 'Название',
      type: 'text',
      required: true,
      placeholder: 'IT Tickets',
    },
    {
      key: 'description',
      label: 'Описание',
      type: 'textarea',
      rows: 3,
      placeholder: 'Описание коллекции для LLM агента...',
    },
  ];

  const [fields, setFields] = useState<FieldFormData[]>([
    {
      id: generateId(),
      name: '',
      type: 'text',
      required: false,
      search_modes: ['exact'],
    },
  ]);

  const createMutation = useMutation({
    mutationFn: collectionsApi.create,
    onSuccess: () => {
      showSuccess('Коллекция создана');
      navigate('/admin/collections');
    },
    onError: (err: Error) => {
      showError(err.message || 'Не удалось создать коллекцию');
    },
  });

  const handleAddField = () => {
    setFields([
      ...fields,
      {
        id: generateId(),
        name: '',
        type: 'text',
        required: false,
        search_modes: ['exact'],
      },
    ]);
  };

  const handleRemoveField = (id: string) => {
    if (fields.length <= 1) {
      showError('Нужно хотя бы одно поле');
      return;
    }
    setFields(fields.filter(f => f.id !== id));
  };

  const handleFieldChange = (
    id: string,
    key: keyof FieldFormData,
    value: string | boolean | SearchMode[]
  ) => {
    setFields(
      fields.map(f => {
        if (f.id !== id) return f;
        const updated = { ...f, [key]: value };
        
        if (key === 'type') {
          updated.search_modes = ['exact'];
        }
        
        return updated;
      })
    );
  };
  
  const toggleSearchMode = (fieldId: string, mode: SearchMode) => {
    setFields(
      fields.map(f => {
        if (f.id !== fieldId) return f;
        
        const modes = new Set(f.search_modes);
        
        if (modes.has(mode)) {
          modes.delete(mode);
          if (modes.size === 0) {
            modes.add('exact');
          }
        } else {
          modes.add(mode);
          if (mode === 'vector' && !modes.has('like')) {
            modes.add('like');
          }
        }
        
        return { ...f, search_modes: Array.from(modes) };
      })
    );
  };

  const handleSave = async () => {
    if (!formData.tenant_id) {
      showError('Выберите тенант');
      return;
    }
    if (!formData.slug) {
      showError('Slug обязателен');
      return;
    }
    if (!formData.name) {
      showError('Название обязательно');
      return;
    }
    if (fields.some(f => !f.name)) {
      showError('Все поля должны иметь имя');
      return;
    }

    const fieldNames = fields.map(f => f.name);
    if (new Set(fieldNames).size !== fieldNames.length) {
      showError('Имена полей должны быть уникальными');
      return;
    }

    const cleanFields: CollectionField[] = fields.map(({ id, ...rest }) => rest);

    await createMutation.mutateAsync({
      tenant_id: formData.tenant_id,
      slug: formData.slug,
      name: formData.name,
      description: formData.description || undefined,
      fields: cleanFields,
    });
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Коллекции', href: '/admin/collections' },
    { label: 'Новая коллекция' },
  ];

  return (
    <EntityPageV2
      title="Новая коллекция"
      mode="create"
      loading={tenantsLoading}
      saving={createMutation.isPending}
      breadcrumbs={breadcrumbs}
      backPath="/admin/collections"
      onSave={handleSave}
      onCancel={() => navigate('/admin/collections')}
    >
      <Tab title="Создание" layout="single">
        <ContentBlock
            title="Основная информация"
            icon="database"
            fields={mainFields}
            data={formData}
            editable={true}
            onChange={(key, value) => {
              if (key === 'slug') {
                setFormData(prev => ({ ...prev, slug: String(value).toLowerCase().replace(/[^a-z0-9_]/g, '') }));
              } else {
                setFormData(prev => ({ ...prev, [key]: value }));
              }
            }}
          />

        <ContentBlock
          title={`Поля (${fields.length})`}
          icon="clipboard-list"
          headerActions={
            <Button type="button" variant="outline" size="sm" onClick={handleAddField}>
              + Добавить поле
            </Button>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {fields.map(field => (
              <FieldEditor
                key={field.id}
                name={field.name}
                type={field.type}
                required={field.required}
                searchModes={field.search_modes}
                onNameChange={(name) => handleFieldChange(field.id, 'name', name)}
                onTypeChange={(type) => handleFieldChange(field.id, 'type', type)}
                onRequiredChange={(required) => handleFieldChange(field.id, 'required', required)}
                onSearchModeToggle={(mode) => toggleSearchMode(field.id, mode as SearchMode)}
                onRemove={() => handleRemoveField(field.id)}
              />
            ))}
          </div>
        </ContentBlock>
      </Tab>
    </EntityPageV2>
  );
}

export default CreateCollectionPage;
