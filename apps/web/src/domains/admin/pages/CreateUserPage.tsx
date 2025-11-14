/**
 * CreateUserPage - Create new user
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateUser } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import styles from './CreateUserPage.module.css';

interface FormData {
  login: string;
  email: string;
  role: 'admin' | 'editor' | 'reader';
  is_active: boolean;
  password: string;
  send_email: boolean;
  require_password_change: boolean;
  tenant_id: string;
}

export function CreateUserPage() {
  const navigate = useNavigate();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();
  const createUser = useCreateUser();
  const { tenants } = useTenants();

  const [formData, setFormData] = useState<FormData>({
    login: '',
    email: '',
    role: 'reader',
    is_active: true,
    password: '',
    send_email: true,
    require_password_change: true,
    tenant_id: tenants?.[0]?.id || '',
  });

  React.useEffect(() => {
    if (tenants.length > 0) {
      setFormData((prev: FormData) =>
        prev.tenant_id ? prev : { ...prev, tenant_id: tenants[0]?.id || '' }
      );
    }
  }, [tenants]);

  const [errors, setErrors] = useState<Partial<FormData>>({});

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrors({});

    // Validation
    if (!formData.login) {
      setErrors({ login: 'Login is required' });
      return;
    }
    if (!formData.password) {
      setErrors({ password: 'Password is required' });
      return;
    }
    if (!formData.tenant_id) {
      setErrors({ tenant_id: 'Tenant is required' });
      return;
    }

    try {
      await createUser.mutateAsync({
        login: formData.login,
        email: formData.email || undefined,
        role: formData.role,
        is_active: formData.is_active,
        password: formData.password,
        send_email: formData.send_email,
        tenant_ids: formData.tenant_id ? [formData.tenant_id] : [],
      });
      showSuccess('User created successfully');
      navigate('/admin/users');
    } catch {
      showError('Failed to create user');
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <h1 className={styles.title}>Create User</h1>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.formGroup}>
            <label>Login *</label>
            <Input
              value={formData.login}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setFormData((prev: FormData) => ({
                  ...prev,
                  login: event.target.value,
                }))
              }
              error={errors.login}
            />
          </div>

          <div className={styles.formGroup}>
            <label>Email</label>
            <Input
              type="email"
              value={formData.email}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setFormData((prev: FormData) => ({
                  ...prev,
                  email: event.target.value,
                }))
              }
              error={errors.email}
            />
          </div>

          <div className={styles.formGroup}>
            <label>Role *</label>
            <Select
              value={formData.role}
              onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
                setFormData((prev: FormData) => ({
                  ...prev,
                  role: event.target.value as FormData['role'],
                }))
              }
            >
              <option value="reader">Reader</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </Select>
          </div>

          <div className={styles.formGroup}>
            <label>Tenant *</label>
            <Select
              value={formData.tenant_id}
              onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
                setFormData((prev: FormData) => ({
                  ...prev,
                  tenant_id: event.target.value,
                }))
              }
              error={errors.tenant_id}
            >
              <option value="">Select tenant</option>
              {tenants.map((tenant: { id: string; name: string }) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </Select>
          </div>

          <div className={styles.formGroup}>
            <label>Password *</label>
            <Input
              type="password"
              value={formData.password}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setFormData((prev: FormData) => ({
                  ...prev,
                  password: event.target.value,
                }))
              }
              error={errors.password}
            />
          </div>

          <div className={styles.formGroup}>
            <label>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData((prev: FormData) => ({
                    ...prev,
                    is_active: event.target.checked,
                  }))
                }
              />
              Active
            </label>
          </div>

          <div className={styles.formGroup}>
            <label>
              <input
                type="checkbox"
                checked={formData.send_email}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData((prev: FormData) => ({
                    ...prev,
                    send_email: event.target.checked,
                  }))
                }
              />
              Send email
            </label>
          </div>

          <div className={styles.formGroup}>
            <label>
              <input
                type="checkbox"
                checked={formData.require_password_change}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setFormData((prev: FormData) => ({
                    ...prev,
                    require_password_change: event.target.checked,
                  }))
                }
              />
              Require password change
            </label>
          </div>

          <div className={styles.formActions}>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/admin/users')}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createUser.isPending}>
              {createUser.isPending ? 'Creating...' : 'Create User'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateUserPage;
