/**
 * UserEditorPage - View/Edit/Create user with EntityPage
 * 
 * Unified page for all user operations:
 * - View: /admin/users/:id (readonly)
 * - Edit: /admin/users/:id?mode=edit
 * - Create: /admin/users/new
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useUser, useUpdateUser, useDeleteUser, useCreateUser } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import Input from '@shared/ui/Input';
import Button from '@shared/ui/Button';
import { Icon } from '@shared/ui/Icon';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { EntityPage, type EntityPageMode } from '@shared/ui/EntityPage';
import { ContentBlock, ContentGrid, type FieldDefinition } from '@shared/ui/ContentBlock';
import type { User, Tenant } from '@shared/api/admin';
import styles from './UserEditorPage.module.css';

const ROLES = [
  { value: 'reader', label: 'Читатель', desc: 'Только просмотр' },
  { value: 'editor', label: 'Редактор', desc: 'Просмотр и редактирование' },
  { value: 'admin', label: 'Администратор', desc: 'Полный доступ' },
];

interface FormData {
  login: string;
  email: string;
  password: string;
  role: User['role'];
  tenant_id: string;
  is_active: boolean;
}

export function UserEditorPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  // Determine mode
  const isCreate = !id;
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isCreate ? 'create' : isEditMode ? 'edit' : 'view';
  const isEditable = mode === 'edit' || mode === 'create';

  const { data: user, isLoading, refetch } = useUser(id);
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const createUser = useCreateUser();
  const { tenants } = useTenants();

  const [formData, setFormData] = useState<FormData>({
    login: '',
    email: '',
    password: '',
    role: 'reader',
    tenant_id: '',
    is_active: true,
  });
  const [newPassword, setNewPassword] = useState('');
  const [saving, setSaving] = useState(false);

  // Field change handler
  const handleFieldChange = (key: string, value: any) => {
    setFormData((prev: FormData) => ({ ...prev, [key]: value }));
  };

  // Field definitions
  const basicInfoFields: FieldDefinition[] = [
    {
      key: 'login',
      label: 'Логин',
      type: 'text',
      required: true,
      placeholder: 'Введите логин',
      disabled: mode !== 'create', // Логин нельзя менять после создания
    },
    {
      key: 'email',
      label: 'Email',
      type: 'text',
      placeholder: 'user@example.com',
    },
    ...(mode === 'create' ? [{
      key: 'password',
      label: 'Пароль',
      type: 'text' as const,
      required: true,
      placeholder: 'Введите пароль',
    }] : []),
    {
      key: 'tenant_id',
      label: 'Тенант',
      type: 'select',
      options: (tenants || []).map((t: Tenant) => ({ value: t.id, label: t.name })),
    },
  ];

  const statusAndRoleFields: FieldDefinition[] = [
    {
      key: 'is_active',
      label: 'Активен',
      type: 'boolean',
      description: 'Пользователь может входить в систему',
    },
    {
      key: 'role',
      label: 'Роль',
      type: 'select',
      options: ROLES.map(r => ({ value: r.value, label: r.label })),
      description: 'Уровень доступа пользователя',
    },
  ];

  useEffect(() => {
    if (user) {
      setFormData({
        login: user.login || '',
        email: user.email || '',
        password: '',
        role: user.role,
        tenant_id: user.tenant_id || '',
        is_active: user.is_active,
      });
    }
  }, [user]);

  // Set default tenant for new users
  useEffect(() => {
    if (isCreate && tenants?.length && !formData.tenant_id) {
      setFormData(prev => ({ ...prev, tenant_id: tenants[0].id }));
    }
  }, [isCreate, tenants, formData.tenant_id]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (mode === 'create') {
        if (!formData.login.trim()) {
          showError('Логин обязателен');
          setSaving(false);
          return;
        }
        if (!formData.password.trim()) {
          showError('Пароль обязателен');
          setSaving(false);
          return;
        }
        await createUser.mutateAsync({
          login: formData.login,
          email: formData.email || undefined,
          password: formData.password,
          role: formData.role,
          tenant_id: formData.tenant_id,
          is_active: formData.is_active,
        });
        showSuccess('Пользователь создан');
        navigate('/admin/users');
      } else {
        await updateUser.mutateAsync({
          id: id!,
          data: {
            email: formData.email || undefined,
            role: formData.role,
            tenant_id: formData.tenant_id,
            is_active: formData.is_active,
          },
        });
        showSuccess('Пользователь обновлён');
        setSearchParams({});
        refetch();
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = () => {
    setSearchParams({ mode: 'edit' });
  };

  const handleCancel = () => {
    if (mode === 'edit' && user) {
      setFormData({
        login: user.login || '',
        email: user.email || '',
        password: '',
        role: user.role,
        tenant_id: user.tenant_id || '',
        is_active: user.is_active,
      });
      setSearchParams({});
    } else if (mode === 'create') {
      navigate('/admin/users');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Удалить этого пользователя?')) return;
    try {
      await deleteUser.mutateAsync(id!);
      showSuccess('Пользователь удалён');
      navigate('/admin/users');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  const handleResetPassword = async () => {
    if (!id || !newPassword.trim()) {
      showError('Введите новый пароль');
      return;
    }
    try {
      await updateUser.mutateAsync({
        id,
        data: { password: newPassword, require_password_change: true },
      });
      showSuccess('Пароль сброшен');
      setNewPassword('');
    } catch {
      showError('Ошибка сброса пароля');
    }
  };

  return (
    <EntityPage
      mode={mode}
      entityName={user?.login || 'Новый пользователь'}
      entityTypeLabel="пользователя"
      backPath="/admin/users"
      loading={!isCreate && isLoading}
      saving={saving}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
      showDelete={mode === 'view' && !!id}
    >
      <ContentGrid>
        {/* Basic Info - 2/3 */}
        <ContentBlock
          width="2/3"
          title="Основная информация"
          icon="user"
          editable={isEditable}
          fields={basicInfoFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Status & Role - 1/3 */}
        <ContentBlock
          width="1/3"
          title="Статус и роль"
          icon="shield"
          editable={isEditable}
          fields={statusAndRoleFields}
          data={formData}
          onChange={handleFieldChange}
        />

        {/* Security Section - 1/2 (есть текстовое поле) */}
        {mode === 'edit' && id && (
          <ContentBlock
            width="1/2"
            title="Сброс пароля"
            icon="key"
          >
            <p className={styles.formHint}>
              Установите новый пароль для пользователя. При следующем входе ему будет предложено сменить пароль.
            </p>
            <div className={styles.passwordRow}>
              <Input
                type="password"
                value={newPassword}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPassword(e.target.value)}
                placeholder="Введите новый пароль"
              />
              <Button 
                variant="outline" 
                onClick={handleResetPassword} 
                disabled={updateUser.isPending || !newPassword.trim()}
              >
                Сбросить
              </Button>
            </div>
          </ContentBlock>
        )}
      </ContentGrid>
    </EntityPage>
  );
}

export default UserEditorPage;
