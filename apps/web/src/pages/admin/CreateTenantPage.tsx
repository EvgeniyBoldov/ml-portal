import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { tenantApi, type TenantCreate, type TenantUpdate } from '@shared/api/tenant';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import styles from './CreateTenantPage.module.css';

interface FormData {
  name: string;
  description: string;
  is_active: boolean;
}

interface FormErrors {
  name?: string;
  description?: string;
  general?: string;
}

export function CreateTenantPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEditing = Boolean(id);
  
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // State
  const [formData, setFormData] = useState<FormData>({
    name: '',
    description: '',
    is_active: true,
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(isEditing);

  // Load tenant data for editing
  useEffect(() => {
    if (isEditing && id) {
      const loadTenant = async () => {
        try {
          setInitialLoading(true);
          const tenant = await tenantApi.getTenant(id);
          setFormData({
            name: tenant.name,
            description: tenant.description || '',
            is_active: tenant.is_active,
          });
        } catch (error) {
          showError('Failed to load tenant data');
          console.error('Error loading tenant:', error);
          navigate('/admin/tenants');
        } finally {
          setInitialLoading(false);
        }
      };

      loadTenant();
    }
  }, [isEditing, id, navigate, showError]);

  // Handle input changes
  const handleInputChange = (field: keyof FormData) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const value = e.target.type === 'checkbox' 
      ? (e.target as HTMLInputElement).checked 
      : e.target.value;
    
    setFormData(prev => ({ ...prev, [field]: value }));
    
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
  };

  // Validate form
  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    // Name validation
    if (!formData.name.trim()) {
      newErrors.name = 'Tenant name is required';
    } else if (formData.name.trim().length < 2) {
      newErrors.name = 'Tenant name must be at least 2 characters';
    } else if (formData.name.trim().length > 100) {
      newErrors.name = 'Tenant name must be less than 100 characters';
    }

    // Description validation
    if (formData.description.length > 500) {
      newErrors.description = 'Description must be less than 500 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);
    setErrors({});

    try {
      const tenantData = {
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
        is_active: formData.is_active,
      };

      if (isEditing && id) {
        await tenantApi.updateTenant(id, tenantData);
        showSuccess(`Tenant "${formData.name}" updated successfully`);
      } else {
        await tenantApi.createTenant(tenantData);
        showSuccess(`Tenant "${formData.name}" created successfully`);
      }

      navigate('/admin/tenants');
    } catch (error) {
      showError(
        isEditing 
          ? 'Failed to update tenant' 
          : 'Failed to create tenant'
      );
      console.error('Error saving tenant:', error);
    } finally {
      setLoading(false);
    }
  };

  // Handle cancel
  const handleCancel = () => {
    navigate('/admin/tenants');
  };

  if (initialLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <div className={styles.loadingSpinner}></div>
          <p>Loading tenant data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>
            {isEditing ? 'Edit Tenant' : 'Create Tenant'}
          </h1>
          <p className={styles.pageDescription}>
            {isEditing 
              ? 'Update tenant information and settings'
              : 'Create a new tenant organization'
            }
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className={styles.form}>
        {errors.general && (
          <div className={styles.formError} style={{ marginBottom: 'var(--spacing-lg)' }}>
            {errors.general}
          </div>
        )}

        {/* Basic Information */}
        <div className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Basic Information</h2>

          <div className={styles.formGrid}>
            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>
                Tenant Name
              </label>
              <Input
                type="text"
                value={formData.name}
                onChange={handleInputChange('name')}
                placeholder="Enter tenant name"
                className={styles.formInput}
                error={!!errors.name}
              />
              {errors.name && (
                <div className={styles.formError}>{errors.name}</div>
              )}
              <div className={styles.formHelp}>
                Unique name for the tenant organization.
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Status</label>
              <select
                value={formData.is_active ? 'active' : 'inactive'}
                onChange={handleInputChange('is_active')}
                className={styles.formSelect}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
              <div className={styles.formHelp}>
                Inactive tenants cannot be used for new user assignments.
              </div>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Description</label>
            <textarea
              value={formData.description}
              onChange={handleInputChange('description')}
              placeholder="Enter tenant description (optional)"
              className={styles.formTextarea}
              rows={4}
            />
            {errors.description && (
              <div className={styles.formError}>{errors.description}</div>
            )}
            <div className={styles.formHelp}>
              Optional description of the tenant organization.
            </div>
          </div>
        </div>

        {/* Form Actions */}
        <div className={styles.formActions}>
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            loading={loading}
            disabled={loading}
          >
            {isEditing ? 'Update Tenant' : 'Create Tenant'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default CreateTenantPage;
