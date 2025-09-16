import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminApi, type UserCreate } from '@shared/api/admin';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import Select from '@shared/ui/Select';
import { useSuccessToast } from '@shared/ui/Toast';
import styles from './CreateUserPage.module.css';

interface FormData {
  login: string;
  email: string;
  role: 'admin' | 'editor' | 'reader';
  is_active: boolean;
  password: string;
  send_email: boolean;
  require_password_change: boolean;
}

interface FormErrors {
  login?: string;
  email?: string;
  password?: string;
  general?: string;
}

export function CreateUserPage() {
  const navigate = useNavigate();
  // const _showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // State
  const [formData, setFormData] = useState<FormData>({
    login: '',
    email: '',
    role: 'reader',
    is_active: true,
    password: '',
    send_email: true,
    require_password_change: true,
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [emailEnabled, setEmailEnabled] = useState(false);

  // Load system status to check if email is enabled
  useEffect(() => {
    const loadSystemStatus = async () => {
      try {
        const status = await adminApi.getSystemStatus();
        setEmailEnabled(status.email_enabled);
        if (!status.email_enabled) {
          setFormData(prev => ({ ...prev, send_email: false }));
        }
      } catch (error) {
        console.error('Failed to load system status:', error);
      }
    };

    loadSystemStatus();
  }, []);

  // Password validation
  const validatePassword = (password: string) => {
    const rules = [
      { test: password.length >= 8, message: 'At least 8 characters' },
      { test: /[A-Z]/.test(password), message: 'One uppercase letter' },
      { test: /[a-z]/.test(password), message: 'One lowercase letter' },
      { test: /\d/.test(password), message: 'One number' },
      {
        test: /[!@#$%^&*(),.?":{}|<>]/.test(password),
        message: 'One special character',
      },
    ];

    return rules.map(rule => ({
      ...rule,
      valid: rule.test,
    }));
  };

  // Form validation
  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    // Login validation
    if (!formData.login.trim()) {
      newErrors.login = 'Login is required';
    } else if (formData.login.length < 3) {
      newErrors.login = 'Login must be at least 3 characters';
    } else if (!/^[a-zA-Z0-9_-]+$/.test(formData.login)) {
      newErrors.login =
        'Login can only contain letters, numbers, hyphens, and underscores';
    }

    // Email validation
    if (formData.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    // Password validation
    if (!formData.send_email) {
      if (!formData.password) {
        newErrors.password = 'Password is required when not sending email';
      } else {
        const passwordRules = validatePassword(formData.password);
        const invalidRules = passwordRules.filter(rule => !rule.valid);
        if (invalidRules.length > 0) {
          newErrors.password = 'Password does not meet requirements';
        }
      }
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
      const userData: UserCreate = {
        login: formData.login.trim(),
        email: formData.email.trim() || undefined,
        role: formData.role,
        is_active: formData.is_active,
        send_email: formData.send_email,
      };

      // Only include password if not sending email
      if (!formData.send_email) {
        userData.password = formData.password;
      }

      const response = await adminApi.createUser(userData);

      showSuccess(
        `User ${formData.login} created successfully${
          response.password ? ` with password: ${response.password}` : ''
        }`
      );

      navigate(`/admin/users/${response.user.id}`);
    } catch (error: any) {
      console.error('Failed to create user:', error);

      if (error.response?.data?.detail?.error?.code === 'user_exists') {
        setErrors({ login: 'User with this login already exists' });
      } else if (
        error.response?.data?.detail?.error?.code === 'invalid_password'
      ) {
        setErrors({ password: error.response.data.detail.error.message });
      } else {
        setErrors({ general: 'Failed to create user. Please try again.' });
      }
    } finally {
      setLoading(false);
    }
  };

  // Handle input changes
  const handleInputChange =
    (field: keyof FormData) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value =
        e.target.type === 'checkbox'
          ? (e.target as HTMLInputElement).checked
          : e.target.value;

      setFormData(prev => ({ ...prev, [field]: value }));

      // Clear error when user starts typing
      if (errors[field as keyof FormErrors]) {
        setErrors(prev => ({ ...prev, [field]: undefined }));
      }
    };

  const passwordRules = validatePassword(formData.password);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Create New User</h1>
        <p className={styles.pageDescription}>
          Create a new user account with appropriate role and permissions.
        </p>
      </div>

      <form onSubmit={handleSubmit} className={styles.form}>
        {errors.general && (
          <div
            className={styles.formError}
            style={{ marginBottom: 'var(--spacing-lg)' }}
          >
            {errors.general}
          </div>
        )}

        {/* Basic Information */}
        <div className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Basic Information</h2>

          <div className={styles.formGrid}>
            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>
                Login
              </label>
              <Input
                type="text"
                value={formData.login}
                onChange={handleInputChange('login')}
                placeholder="Enter username"
                className={styles.formInput}
                error={!!errors.login}
              />
              {errors.login && (
                <div className={styles.formError}>{errors.login}</div>
              )}
              <div className={styles.formHelp}>
                Username for login. Only letters, numbers, hyphens, and
                underscores allowed.
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Email</label>
              <Input
                type="email"
                value={formData.email}
                onChange={handleInputChange('email')}
                placeholder="Enter email address"
                className={styles.formInput}
                error={!!errors.email}
              />
              {errors.email && (
                <div className={styles.formError}>{errors.email}</div>
              )}
              <div className={styles.formHelp}>
                Optional email address for notifications.
              </div>
            </div>
          </div>

          <div className={styles.formGrid}>
            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>
                Role
              </label>
              <Select
                value={formData.role}
                onChange={handleInputChange('role')}
                className={styles.formSelect}
              >
                <option value="reader">Reader - View only access</option>
                <option value="editor">Editor - Create and edit content</option>
                <option value="admin">Admin - Full system access</option>
              </Select>
              <div className={styles.formHelp}>
                Determines user permissions and access level.
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Status</label>
              <Select
                value={formData.is_active ? 'active' : 'inactive'}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    is_active: e.target.value === 'active',
                  }))
                }
                className={styles.formSelect}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </Select>
              <div className={styles.formHelp}>
                Inactive users cannot log in to the system.
              </div>
            </div>
          </div>
        </div>

        {/* Password Settings */}
        <div className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Password Settings</h2>

          {emailEnabled && (
            <div className={styles.passwordToggle}>
              <label className={styles.passwordToggleLabel}>
                <input
                  type="checkbox"
                  checked={formData.send_email}
                  onChange={handleInputChange('send_email')}
                  className={styles.formCheckboxInput}
                />
                Send password setup link via email
              </label>
              <div
                className={`${styles.passwordToggleSwitch} ${formData.send_email ? styles.active : ''}`}
                onClick={() =>
                  setFormData(prev => ({
                    ...prev,
                    send_email: !prev.send_email,
                  }))
                }
              />
            </div>
          )}

          {!formData.send_email && (
            <div className={styles.passwordField}>
              <div className={styles.formGroup}>
                <label className={`${styles.formLabel} ${styles.required}`}>
                  Temporary Password
                </label>
                <Input
                  type="password"
                  value={formData.password}
                  onChange={handleInputChange('password')}
                  placeholder="Enter temporary password"
                  className={styles.formInput}
                  error={!!errors.password}
                />
                {errors.password && (
                  <div className={styles.formError}>{errors.password}</div>
                )}
                <div className={styles.formHelp}>
                  User will be required to change this password on first login.
                </div>
              </div>

              <div className={styles.passwordPolicy}>
                <div className={styles.passwordPolicyTitle}>
                  Password Requirements:
                </div>
                <ul className={styles.passwordPolicyList}>
                  {passwordRules.map((rule, index) => (
                    <li
                      key={index}
                      className={`${styles.passwordPolicyItem} ${rule.valid ? styles.valid : styles.invalid}`}
                    >
                      <span className={styles.passwordPolicyIcon}>
                        {rule.valid ? '✓' : '✕'}
                      </span>
                      {rule.message}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.formCheckbox}>
              <input
                type="checkbox"
                checked={formData.require_password_change}
                onChange={handleInputChange('require_password_change')}
                className={styles.formCheckboxInput}
              />
              <span className={styles.formCheckboxLabel}>
                Require password change on first login
              </span>
            </label>
            <div className={styles.formHelp}>
              User must set a new password when they first log in.
            </div>
          </div>
        </div>

        {/* Form Actions */}
        <div className={styles.formActions}>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/admin/users')}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? 'Creating...' : 'Create User'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default CreateUserPage;
