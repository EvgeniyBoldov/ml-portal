/**
 * CreateCollectionPage - Create a new collection
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { Skeleton } from '@shared/ui/Skeleton';
import { collectionsApi, type CollectionField } from '@shared/api/collections';
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

const SEARCH_MODES = [
  { value: 'exact', label: 'Exact' },
  { value: 'like', label: 'LIKE' },
  { value: 'range', label: 'Range' },
];

function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

export function CreateCollectionPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const { tenants, loading: tenantsLoading } = useTenants();

  const [formData, setFormData] = useState({
    tenant_id: '',
    slug: '',
    name: '',
    description: '',
    type: 'sql' as const,
  });

  const [fields, setFields] = useState<FieldFormData[]>([
    {
      id: generateId(),
      name: '',
      type: 'text',
      required: false,
      searchable: true,
      search_mode: 'like',
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
        searchable: true,
        search_mode: 'like',
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
    value: string | boolean
  ) => {
    setFields(
      fields.map(f => {
        if (f.id !== id) return f;
        const updated = { ...f, [key]: value };
        if (key === 'type') {
          if (value === 'text') {
            updated.search_mode = 'like';
          } else if (['integer', 'float', 'datetime', 'date'].includes(value as string)) {
            updated.search_mode = 'range';
          } else {
            updated.search_mode = 'exact';
          }
        }
        return updated;
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
      type: formData.type,
      fields: cleanFields,
    });
  };

  if (tenantsLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <Skeleton width={400} height={300} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Create Collection</h1>
        <p className={styles.pageDescription}>
          Создайте новую коллекцию данных для хранения структурированной информации
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
                {tenants.map(t => (
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

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Type</label>
              <select
                className={styles.formSelect}
                value={formData.type}
                onChange={e =>
                  setFormData({ ...formData, type: e.target.value as 'sql' })
                }
              >
                <option value="sql">SQL</option>
                <option value="vector" disabled>
                  Vector (coming soon)
                </option>
                <option value="hybrid" disabled>
                  Hybrid (coming soon)
                </option>
              </select>
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

          <div className={styles.fieldsList}>
            {fields.length === 0 ? (
              <div className={styles.emptyFields}>
                Добавьте хотя бы одно поле
              </div>
            ) : (
              fields.map(field => (
                <div key={field.id} className={styles.fieldRow}>
                  <input
                    type="text"
                    className={styles.fieldInput}
                    value={field.name}
                    onChange={e =>
                      handleFieldChange(
                        field.id,
                        'name',
                        e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '')
                      )
                    }
                    placeholder="field_name"
                  />
                  <select
                    className={styles.fieldSelect}
                    value={field.type}
                    onChange={e =>
                      handleFieldChange(field.id, 'type', e.target.value)
                    }
                  >
                    {FIELD_TYPES.map(t => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                  <select
                    className={styles.fieldSelect}
                    value={field.search_mode || 'exact'}
                    onChange={e =>
                      handleFieldChange(field.id, 'search_mode', e.target.value)
                    }
                  >
                    {SEARCH_MODES.map(m => (
                      <option
                        key={m.value}
                        value={m.value}
                        disabled={
                          (m.value === 'like' && field.type !== 'text') ||
                          (m.value === 'range' &&
                            !['integer', 'float', 'datetime', 'date'].includes(
                              field.type
                            ))
                        }
                      >
                        {m.label}
                      </option>
                    ))}
                  </select>
                  <label className={styles.fieldCheckbox}>
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={e =>
                        handleFieldChange(field.id, 'required', e.target.checked)
                      }
                    />
                    Required
                  </label>
                  <label className={styles.fieldCheckbox}>
                    <input
                      type="checkbox"
                      checked={field.searchable}
                      onChange={e =>
                        handleFieldChange(field.id, 'searchable', e.target.checked)
                      }
                    />
                    Searchable
                  </label>
                  <button
                    type="button"
                    className={styles.removeFieldBtn}
                    onClick={() => handleRemoveField(field.id)}
                    title="Remove field"
                  >
                    ✕
                  </button>
                </div>
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
