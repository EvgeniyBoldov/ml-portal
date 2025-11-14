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
  embed_models: string[];
  rerank_model: string;
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
    embed_models: [],
    rerank_model: '',
    ocr: false,
    layout: false,
  });

  React.useEffect(() => {
    if (tenantData) {
      setFormData({
        name: tenantData.name || '',
        description: tenantData.description || '',
        is_active: tenantData.is_active ?? true,
        embed_models: tenantData.embed_models || [],
        rerank_model: tenantData.rerank_model || '',
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

    // Validate embed models
    if (formData.embed_models.length > 2) {
      showError('Maximum 2 embedding models allowed');
      return;
    }

    try {
      if (isEditing) {
        await tenantApi.updateTenant(id!, {
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          embed_models: formData.embed_models,
          rerank_model: formData.rerank_model || undefined,
          ocr: formData.ocr,
          layout: formData.layout,
        });
        showSuccess('Tenant updated successfully');
      } else {
        await tenantApi.createTenant({
          name: formData.name,
          description: formData.description,
          is_active: formData.is_active,
          embed_models: formData.embed_models,
          rerank_model: formData.rerank_model || undefined,
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
    m =>
      m.modality === 'text' && (m.state === 'active' || m.state === 'archived')
  );
  const rerankModels = models.filter(
    m =>
      m.modality === 'rerank' &&
      (m.state === 'active' || m.state === 'archived')
  );

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

          {/* Embedding Models */}
          <div className={styles.formGroup}>
            <label>Embedding Models (max 2)</label>
            <div className={styles.multiSelect}>
              {textModels.map(model => (
                <label key={model.model} className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={formData.embed_models.includes(model.model)}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                      if (event.target.checked) {
                        if (formData.embed_models.length < 2) {
                          setFormData(prev => ({
                            ...prev,
                            embed_models: [...prev.embed_models, model.model],
                          }));
                        }
                      } else {
                        setFormData(prev => ({
                          ...prev,
                          embed_models: prev.embed_models.filter(
                            m => m !== model.model
                          ),
                        }));
                      }
                    }}
                    disabled={
                      formData.embed_models.length >= 2 &&
                      !formData.embed_models.includes(model.model)
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
              Select up to 2 embedding models for text processing.
            </div>
          </div>

          {/* Rerank Model */}
          <div className={styles.formGroup}>
            <label>Rerank Model</label>
            <div className={styles.multiSelect}>
              {rerankModels.map(model => (
                <label key={model.model} className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={formData.rerank_model === model.model}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                      if (event.target.checked) {
                        setFormData(prev => ({
                          ...prev,
                          rerank_model: model.model,
                        }));
                      } else {
                        setFormData(prev => ({ ...prev, rerank_model: '' }));
                      }
                    }}
                  />
                  <span>
                    {model.model} ({model.version})
                    {model.state === 'archived' && ' (archived)'}
                  </span>
                </label>
              ))}
            </div>
            <div className={styles.formHelp}>
              Optional rerank model for improving search results.
            </div>
          </div>

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
