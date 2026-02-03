/**
 * CreateUserPage - Создание нового пользователя
 * Переделано в стиле проекта с красивыми компонентами
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateUser } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import { Select } from '@shared/ui';
import Toggle from '@shared/ui/Toggle';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import styles from './CreateUserPage.module.css';

type UserRole = 'admin' | 'editor' | 'reader';

interface FormData {
  login: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  password: string;
  tenant_id: string;
}

const ROLES: { value: UserRole; label: string; description: string }[] = [
  { value: 'reader', label: 'Читатель', description: 'Только просмотр' },
  { value: 'editor', label: 'Редактор', description: 'Просмотр и редактирование' },
  { value: 'admin', label: 'Администратор', description: 'Полный доступ' },
];

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
    tenant_id: '',
  });

  const [errors, setErrors] = useState<Partial<Record<keyof FormData, string>>>({});
  const [generatePassword, setGeneratePassword] = useState(false);

  useEffect(() => {
    if (tenants.length > 0 && !formData.tenant_id) {
      setFormData(prev => ({ ...prev, tenant_id: tenants[0]?.id || '' }));
    }
  }, [tenants, formData.tenant_id]);

  const generateRandomPassword = () => {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
    let password = '';
    for (let i = 0; i < 16; i++) {
      password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return password;
  };

  const handleGeneratePassword = () => {
    const newPassword = generateRandomPassword();
    setFormData(prev => ({ ...prev, password: newPassword }));
    setGeneratePassword(true);
  };

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof FormData, string>> = {};

    if (!formData.login.trim()) {
      newErrors.login = 'Логин обязателен';
    } else if (formData.login.length < 3) {
      newErrors.login = 'Минимум 3 символа';
    }

    if (formData.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Некорректный email';
    }

    if (!formData.password) {
      newErrors.password = 'Пароль обязателен';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Минимум 8 символов';
    }

    if (!formData.tenant_id) {
      newErrors.tenant_id = 'Выберите тенант';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    if (!validate()) return;

    try {
      await createUser.mutateAsync({
        login: formData.login,
        email: formData.email || undefined,
        role: formData.role,
        is_active: formData.is_active,
        password: formData.password,
        tenant_ids: [formData.tenant_id],
      });
      showSuccess('Пользователь успешно создан');
      navigate('/admin/users');
    } catch {
      showError('Не удалось создать пользователя');
    }
  };

  const updateField = <K extends keyof FormData>(field: K, value: FormData[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Создание пользователя</h1>
        <p className={styles.pageDescription}>
          Заполните информацию для создания нового пользователя системы
        </p>
      </div>

      <form onSubmit={handleSubmit} className={styles.form}>
        {/* Основная информация */}
        <section className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Основная информация</h2>
          
          <div className={styles.formGrid}>
            <div className={styles.formGroup}>
              <label className={`${styles.formLabel} ${styles.required}`}>Логин</label>
              <Input
                value={formData.login}
                onChange={e => updateField('login', e.target.value)}
                placeholder="username"
                error={!!errors.login}
                className={styles.formInput}
              />
              {errors.login && <span className={styles.formError}>{errors.login}</span>}
            </div>

            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Email</label>
              <Input
                type="email"
                value={formData.email}
                onChange={e => updateField('email', e.target.value)}
                placeholder="user@example.com"
                error={!!errors.email}
                className={styles.formInput}
              />
              {errors.email && <span className={styles.formError}>{errors.email}</span>}
            </div>

            <div className={`${styles.formGroup} ${styles.fullWidth}`}>
              <label className={`${styles.formLabel} ${styles.required}`}>Тенант</label>
              <Select
                value={formData.tenant_id}
                onChange={(value) => updateField('tenant_id', value)}
                placeholder="Выберите тенант"
                options={[
                  { value: '', label: 'Выберите тенант' },
                  ...tenants.map(tenant => ({ value: tenant.id, label: tenant.name }))
                ]}
              />
              {errors.tenant_id && <span className={styles.formError}>{errors.tenant_id}</span>}
            </div>

            <div className={`${styles.formGroup} ${styles.fullWidth}`}>
              <Toggle
                checked={formData.is_active}
                onChange={checked => updateField('is_active', checked)}
                label="Активен"
                description="Пользователь может входить в систему"
              />
            </div>
          </div>
        </section>

        {/* Роль */}
        <section className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Роль</h2>
          
          <div className={styles.roleGrid}>
            {ROLES.map(role => (
              <button
                key={role.value}
                type="button"
                className={`${styles.roleCard} ${formData.role === role.value ? styles.roleCardActive : ''}`}
                onClick={() => updateField('role', role.value)}
              >
                <span className={styles.roleLabel}>{role.label}</span>
                <span className={styles.roleDescription}>{role.description}</span>
                {formData.role === role.value && (
                  <span className={styles.roleCheck}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </span>
                )}
              </button>
            ))}
          </div>
        </section>

        {/* Безопасность */}
        <section className={styles.formSection}>
          <h2 className={styles.sectionTitle}>Безопасность</h2>
          
          <div className={styles.formGrid}>
            <div className={`${styles.formGroup} ${styles.fullWidth}`}>
              <label className={`${styles.formLabel} ${styles.required}`}>Пароль</label>
              <div className={styles.passwordField}>
                <Input
                  type={generatePassword ? 'text' : 'password'}
                  value={formData.password}
                  onChange={e => {
                    updateField('password', e.target.value);
                    setGeneratePassword(false);
                  }}
                  placeholder="Минимум 8 символов"
                  error={!!errors.password}
                  className={styles.formInput}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleGeneratePassword}
                  className={styles.generateBtn}
                >
                  Сгенерировать
                </Button>
              </div>
              {errors.password && <span className={styles.formError}>{errors.password}</span>}
              {generatePassword && (
                <span className={styles.formHelp}>
                  Пароль сгенерирован. Скопируйте его перед сохранением.
                </span>
              )}
            </div>
          </div>
        </section>

        {/* Действия */}
        <div className={styles.formActions}>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/admin/users')}
          >
            Отмена
          </Button>
          <Button type="submit" disabled={createUser.isPending}>
            {createUser.isPending ? 'Создание...' : 'Создать пользователя'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default CreateUserPage;
