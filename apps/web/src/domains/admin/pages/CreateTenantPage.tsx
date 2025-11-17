/**
 * CreateTenantPage - Create/edit tenant with model selection
 */
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTenant, useModels } from '@shared/api/hooks/useAdmin';
import { tenantApi } from '@shared/api/tenant';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { Skeleton } from '@shared/ui/Skeleton';
import styles from './CreateTenantPage.module.css';

interface FormData {
  name: string;
  description: string;
  is_active: boolean;
  extra_embed_model: string | '';
  ocr: boolean;
  layout: boolean;
}

export function CreateTenantPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isEditing = !!id;
  const { data: tenantData, isLoading: tenantLoading } = useTenant(id);
  const { data: modelsData, isLoading: modelsLoading } = useModels({
    size: 100,
  });

  const [formData, setFormData] = useState<FormData>({
    name: '',
    description: '',
    is_active: true,
    extra_embed_model: '',
    ocr: false,
    layout: false,
  });

  React.useEffect(() => {
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

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!formData.name) {
      showError('Name is required');
      return;
    }

    try {
      if (isEditing) {
        await tenantApi.updateTenant(id!, {
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || null,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Tenant updated successfully');
      } else {
        await tenantApi.createTenant({
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          extra_embed_model: formData.extra_embed_model || undefined,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Tenant created successfully');
      }
      navigate('/admin/tenants');
    } catch {
      showError('Failed to save tenant');
    }
  };

  if ((isEditing && tenantLoading) || modelsLoading) {
    return (
      <div className={styles.wrap}>
        <div className={styles.card}>
          <Skeleton width={400} height={300} />
        </div>
      </div>
    );
  }

  const models = modelsData?.items || [];
  const textModels = models.filter(
    m => m.modality === 'text' && (m.state === 'active' || m.state === 'archived')
  );
  const globalEmbed = textModels.find(m => (m as any).global === true);
  const nonGlobalText = textModels.filter(m => !(m as any).global);

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <h1 className={styles.title}>
          {isEditing ? 'Edit Tenant' : 'Create Tenant'}
        </h1>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.formGroup}>
            <label>Name *</label>
            <Input
              value={formData.name}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setFormData(prev => ({ ...prev, name: event.target.value }))
              }
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label>Description</label>
            <Input
              value={formData.description}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setFormData(prev => ({
                  ...prev,
                  description: event.target.value,
                }))
              }
            />
          </div>

          <div className={styles.formGroup}>
            <label>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData(prev => ({
                    ...prev,
                    is_active: event.target.checked,
                  }))
                }
              />
              Active
            </label>
          </div>

          {/* Embedding Model: global + one extra */}
          <div className={styles.formGroup}>
            <label>Embedding Model</label>
            <div className={styles.multiSelect}>
              {globalEmbed && (
                <label className={styles.checkboxLabel}>
                  <input type="checkbox" checked readOnly disabled />
                  <span>
                    {globalEmbed.model} ({globalEmbed.version}) — global
                  </span>
                </label>
              )}
              <div className={styles.formHelp}>Optional extra model:</div>
              <label className={styles.checkboxLabel}>
                <input
                  type="radio"
                  name="extraEmbed"
                  checked={formData.extra_embed_model === ''}
                  onChange={() => setFormData(prev => ({ ...prev, extra_embed_model: '' }))}
                />
                <span>None</span>
              </label>
              {nonGlobalText.map(model => (
                <label key={model.model} className={styles.checkboxLabel}>
                  <input
                    type="radio"
                    name="extraEmbed"
                    checked={formData.extra_embed_model === model.model}
                    onChange={() =>
                      setFormData(prev => ({ ...prev, extra_embed_model: model.model }))
                    }
                  />
                  <span>
                    {model.model} ({model.version})
                    {model.state === 'archived' && ' (archived)'}
                  </span>
                </label>
              ))}
            </div>
            <div className={styles.formHelp}>
              Global model is applied automatically. You can select at most one additional embedding model.
            </div>
          </div>

          {/* Rerank selection removed: rerank is global-only */}

          {/* OCR and Layout */}
          <div className={styles.formGroup}>
            <label>
              <input
                type="checkbox"
                checked={formData.ocr}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData(prev => ({ ...prev, ocr: event.target.checked }))
                }
              />
              OCR (Optical Character Recognition)
            </label>
          </div>

          <div className={styles.formGroup}>
            <label>
              <input
                type="checkbox"
                checked={formData.layout}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData(prev => ({
                    ...prev,
                    layout: event.target.checked,
                  }))
                }
              />
              Layout Analysis
            </label>
          </div>

          <div className={styles.formActions}>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/admin/tenants')}
            >
              Cancel
            </Button>
            <Button type="submit">{isEditing ? 'Update' : 'Create'}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateTenantPage;
