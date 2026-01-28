/**
 * CreateCollectionPage - Create a new collection
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import FieldEditor from '@shared/ui/FieldEditor';
import FieldCard from '@shared/ui/FieldCard';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { collectionsApi, CollectionField, SearchMode } from '@shared/api/collections';
import { adminApi } from '@shared/api/admin';
import styles from './CreateCollectionPage.module.css';

interface FieldFormData extends CollectionField {
  id: string;
}

const FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'integer', label: 'Integer' },
  { value: 'float', label: 'Float' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'datetime', label: 'DateTime' },
  { value: 'date', label: 'Date' },
];

function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

export function CreateCollectionPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const { data: tenants, isLoading: tenantsLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: async () => {
      const response = await adminApi.getTenants();
      return response.data;
    },
  });

  const [formData, setFormData] = useState({
    tenant_id: '',
    slug: '',
    name: '',
    description: '',
  });

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
        
        // Reset search_modes when type changes
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
          // Always keep at least 'exact'
          if (modes.size === 0) {
            modes.add('exact');
          }
        } else {
          modes.add(mode);
          // If adding vector, ensure like is also present
          if (mode === 'vector' && !modes.has('like')) {
            modes.add('like');
          }
        }
        
        return { ...f, search_modes: Array.from(modes) };
      })
    );
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

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

  if (tenantsLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <div className={styles.emptyIcon}>🔄</div>
          <h3>Loading...</h3>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Create Collection</h1>
        <p className={styles.pageDescription}>
          Создайте коллекцию для структурированных данных. Векторный поиск включается автоматически для текстовых полей с LIKE.
        </p>
      </div>

      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Basic Info</h2>
          <div className={styles.formGrid}>
            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>
                Tenant
              </label>
              <select
                className={styles.formSelect}
                value={formData.tenant_id}
                onChange={e =>
                  setFormData({ ...formData, tenant_id: e.target.value })
                }
              >
                <option value="">Select tenant...</option>
                {tenants?.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>
                Slug
              </label>
              <input
                type="text"
                className={styles.formInput}
                value={formData.slug}
                onChange={e =>
                  setFormData({
                    ...formData,
                    slug: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''),
                  })
                }
                placeholder="tickets"
              />
              <span className={styles.formHelp}>
                Уникальный идентификатор (a-z, 0-9, _)
              </span>
            </div>

            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>
                Name
              </label>
              <input
                type="text"
                className={styles.formInput}
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                placeholder="IT Tickets"
              />
            </div>

            <div className={`${styles.formGroup} ${styles.fullWidth}`}>
              <label className={styles.formLabel}>Description</label>
              <textarea
                className={styles.formTextarea}
                value={formData.description}
                onChange={e =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="Описание коллекции для LLM агента..."
              />
              <span className={styles.formHelp}>
                Это описание будет использоваться агентом для понимания содержимого
              </span>
            </div>
          </div>
        </div>

        <div className={styles.formSection}>
          <div className={styles.fieldsHeader}>
            <h2 className={styles.sectionTitle} style={{ margin: 0, border: 'none', padding: 0 }}>
              Fields
            </h2>
            <Button type="button" variant="secondary" onClick={handleAddField}>
              + Add Field
            </Button>
          </div>

          <div className={styles.fieldsContainer}>
            {fields.length === 0 ? (
              <div className={styles.emptyState}>
                <div className={styles.emptyIcon}>📋</div>
                <h3>No fields yet</h3>
                <p>Add fields to define your collection schema</p>
              </div>
            ) : (
              fields.map(field => (
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
              ))
            )}
          </div>
        </div>

        <div className={styles.formActions}>
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate('/admin/collections')}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Creating...' : 'Create Collection'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default CreateCollectionPage;
