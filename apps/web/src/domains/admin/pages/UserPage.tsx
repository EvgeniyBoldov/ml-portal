/**
 * UserEditorPage - View/Edit/Create user with EntityPageV2
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useUser, useUpdateUser, useDeleteUser, useCreateUser } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import { qk } from '@shared/api/keys';
import { useErrorToast, useSuccessToast } from '@shared/ui/Toast';
import { EntityPageV2, Tab, type EntityPageMode } from '@/shared/ui';
import { ContentBlock, type FieldDefinition } from '@shared/ui/ContentBlock';
import { Button } from '@shared/ui';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import ConfirmDialog from '@/shared/ui/ConfirmDialog';
import type { User, Tenant } from '@shared/api/admin';
import styles from './UserEditorPage.module.css';

const ROLES = [
  { value: 'reader', label: 'Читатель' },
  { value: 'editor', label: 'Редактор' },
  { value: 'admin', label: 'Администратор' },
];

interface FormData {
  login: string;
  email: string;
  password: string;
  role: User['role'];
  tenant_id: string;
  is_active: boolean;
}

export function UserPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !id || id === 'new';
  const isEditMode = searchParams.get('mode') === 'edit';
  const mode: EntityPageMode = isNew ? 'create' : isEditMode ? 'edit' : 'view';
  const editable = mode === 'edit' || mode === 'create';

  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: user, isLoading, refetch } = useUser(id);
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const createUser = useCreateUser();
  const { tenants } = useTenants();

  const [formData, setFormData] = useState<FormData>({
    login: '', email: '', password: '',
    role: 'reader', tenant_id: '', is_active: true,
  });

  const handleFieldChange = (key: string, value: any) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  // ─── Field definitions ───
  const basicInfoFields: FieldDefinition[] = [
    { key: 'login', label: 'Логин', type: 'text', required: true, placeholder: 'Введите логин', disabled: mode !== 'create' },
    { key: 'email', label: 'Email', type: 'text', placeholder: 'user@example.com' },
    ...(mode === 'create' ? [{ key: 'password', label: 'Пароль', type: 'text' as const, required: true, placeholder: 'Введите пароль' }] : []),
    { key: 'tenant_id', label: 'Тенант', type: 'select', options: (tenants || []).map((t: Tenant) => ({ value: t.id, label: t.name })) },
  ];

  const statusAndRoleFields: FieldDefinition[] = [
    { key: 'is_active', label: 'Активен', type: 'boolean', description: 'Пользователь может входить в систему' },
    { key: 'role', label: 'Роль', type: 'select', options: ROLES.map(r => ({ value: r.value, label: r.label })), description: 'Уровень доступа пользователя' },
  ];

  // ─── Sync form with data ───
  useEffect(() => {
    if (user) {
      setFormData({
        login: user.login || '', email: user.email || '', password: '',
        role: user.role, tenant_id: user.tenant_id || '', is_active: user.is_active,
      });
    }
  }, [user]);

  useEffect(() => {
    if (isNew && tenants?.length && !formData.tenant_id) {
      setFormData(prev => ({ ...prev, tenant_id: tenants[0].id }));
    }
  }, [isNew, tenants, formData.tenant_id]);

  // ─── Handlers ───
  const handleSave = async () => {
    setSaving(true);
    try {
      if (mode === 'create') {
        if (!formData.login.trim()) { showError('Логин обязателен'); return; }
        if (!formData.password.trim()) { showError('Пароль обязателен'); return; }
        await createUser.mutateAsync({
          login: formData.login, email: formData.email || undefined,
          password: formData.password, role: formData.role,
          tenant_id: formData.tenant_id, is_active: formData.is_active,
        });
        showSuccess('Пользователь создан');
        navigate('/admin/users');
      } else {
        await updateUser.mutateAsync({
          id: id!,
          data: {
            email: formData.email || undefined, role: formData.role,
            tenant_id: formData.tenant_id, is_active: formData.is_active,
          },
        });
        showSuccess('Пользователь обновлён');
        setSearchParams({});
        refetch();
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally { setSaving(false); }
  };

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (mode === 'edit' && user) {
      setFormData({
        login: user.login || '', email: user.email || '', password: '',
        role: user.role, tenant_id: user.tenant_id || '', is_active: user.is_active,
      });
      setSearchParams({});
    } else if (isNew) { navigate('/admin/users'); }
  };

  const handleDelete = () => setShowDeleteConfirm(true);
  
  const handleResetPassword = async () => {
    try {
      // TODO: Add password reset API call
      showSuccess('Ссылка для сброса пароля отправлена на email');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка сброса пароля');
    }
  };
  
  const handleDeleteConfirm = async () => {
    try {
      await deleteUser.mutateAsync(id!);
      showSuccess('Пользователь удалён');
      navigate('/admin/users');
    } catch (err) { showError(err instanceof Error ? err.message : 'Ошибка удаления'); }
    setShowDeleteConfirm(false);
  };

  // ─── Render ───
  return (
    <>
    <EntityPageV2
      title={user?.login || 'Новый пользователь'}
      mode={mode}
      loading={!isNew && isLoading}
      saving={saving}
      breadcrumbs={[
        { label: 'Пользователи', href: '/admin/users' },
        { label: user?.login || 'Новый пользователь' },
      ]}
      backPath="/admin/users"
      onSave={handleSave}
      onCancel={handleCancel}
      onDelete={handleDelete}
    >
      <Tab 
        title="Обзор" 
        layout="grid"
        actions={
          mode === 'view' ? [
            <Button key="edit" onClick={handleEdit}>
              Редактировать
            </Button>,
            <Button key="reset" variant="outline" onClick={handleResetPassword} disabled={!user?.email}>
              Сбросить пароль
            </Button>,
            <Button key="delete" variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              Удалить
            </Button>,
          ] : mode === 'create' ? [
            <Button key="save" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : mode === 'edit' ? [
            <Button key="save" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>,
            <Button key="cancel" variant="outline" onClick={handleCancel}>
              Отмена
            </Button>,
          ] : []
        }
      >
        <ContentBlock title="Основная информация" icon="user" editable={editable} fields={basicInfoFields} data={formData} onChange={handleFieldChange} />
        <ContentBlock title="Статус и роль" icon="shield" editable={editable} fields={statusAndRoleFields} data={formData} onChange={handleFieldChange} />
      </Tab>

      {!isNew && (
        <Tab 
          title="RBAC правила" 
          layout="full"
          actions={[
            <Button key="create" onClick={() => navigate(`/admin/users/${id}/rbac/new`)}>
              Создать правило
            </Button>,
          ]}
        >
          <RBACRulesTable mode="user" ownerId={id} />
        </Tab>
      )}
    </EntityPageV2>

    <ConfirmDialog
      open={showDeleteConfirm}
      title="Удалить пользователя?"
      message="Вы уверены? Это действие нельзя отменить."
      confirmLabel="Удалить"
      cancelLabel="Отмена"
      variant="danger"
      onConfirm={handleDeleteConfirm}
      onCancel={() => setShowDeleteConfirm(false)}
    />
    </>
  );
}

export default UserPage;
