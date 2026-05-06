/**
 * UserPage - Admin page for managing Users
 * 
 * Uses Block + GridLayout system for structured layout.
 * Data flows: API types → formData state → Block fields.
 * No mappers, no intermediate interfaces.
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useUser, useUpdateUser, useDeleteUser, useCreateUser, useSetUserPassword } from '@shared/api/hooks/useAdmin';
import { useTenants } from '@shared/hooks/useTenants';
import { qk } from '@shared/api/keys';
import { useErrorToast, useSuccessToast } from '@/shared/ui/Toast';
import { EntityPageV2, Tab, type BreadcrumbItem, type EntityPageMode } from '@/shared/ui/EntityPage';
import { Block, type FieldConfig } from '@/shared/ui/GridLayout';
import { Button, ConfirmDialog, Modal } from '@/shared/ui';
import default as Input from '@/shared/ui/Input';
import { RBACRulesTable } from '@/shared/ui/RBACRulesTable';
import type { User, Tenant } from '@shared/api/admin';

/* ─── SetPasswordModal ─── */

function SetPasswordModal({
  open,
  onClose,
  onConfirm,
  saving,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (password: string) => void;
  saving: boolean;
}) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setPassword(''); setConfirm(''); setError(''); setRevealed(false); }
  }, [open]);

  const handleSubmit = () => {
    if (password.length < 8) { setError('Минимум 8 символов'); return; }
    if (password !== confirm) { setError('Пароли не совпадают'); return; }
    setError('');
    onConfirm(password);
  };

  return (
    <Modal
      open={open}
      title="Установить пароль"
      onClose={onClose}
      footer={
        <>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? 'Сохранение...' : 'Установить'}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={saving}>Отмена</Button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <label style={{ display: 'block', marginBottom: '0.375rem', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)' }}>Новый пароль</label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Input
              type={revealed ? 'text' : 'password'}
              value={password}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
              placeholder="Минимум 8 символов"
              autoComplete="new-password"
            />
            <Button size="sm" variant="ghost" onClick={() => setRevealed(v => !v)} type="button">
              {revealed ? '🙈' : '👁'}
            </Button>
          </div>
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.375rem', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)' }}>Повторите пароль</label>
          <Input
            type={revealed ? 'text' : 'password'}
            value={confirm}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirm(e.target.value)}
            placeholder="Повторите пароль"
            autoComplete="new-password"
          />
        </div>
        {error && (
          <div style={{ color: 'var(--color-danger, #e74c3c)', fontSize: '0.875rem' }}>{error}</div>
        )}
      </div>
    </Modal>
  );
}

/* ─── Constants ─── */

const ROLES = [
  { value: 'reader', label: 'Читатель' },
  { value: 'editor', label: 'Редактор' },
  { value: 'admin', label: 'Администратор' },
];

/* ─── Field configs ─── */

const BASE_INFO_FIELDS: Omit<FieldConfig, 'options'>[] = [
  {
    key: 'login',
    type: 'text',
    label: 'Логин',
    description: 'Уникальный идентификатор пользователя',
    editable: false,
    placeholder: 'Введите логин',
  },
  {
    key: 'email',
    type: 'text',
    label: 'Email',
    placeholder: 'user@example.com',
  },
  {
    key: 'tenant_id',
    type: 'select',
    label: 'Тенант',
    description: 'Основной тенант пользователя',
  },
];

const BASE_INFO_FIELDS_CREATE: Omit<FieldConfig, 'options'>[] = [
  {
    key: 'login',
    type: 'text',
    label: 'Логин',
    description: 'Уникальный идентификатор пользователя',
    editable: true,
    placeholder: 'Введите логин',
  },
  {
    key: 'email',
    type: 'text',
    label: 'Email',
    placeholder: 'user@example.com',
  },
  {
    key: 'tenant_id',
    type: 'select',
    label: 'Тенант',
    description: 'Основной тенант пользователя',
  },
];

const HIDDEN_BASE_INFO_FIELDS: Omit<FieldConfig, 'options'>[] = [
];

const STATUS_FIELDS: FieldConfig[] = [
  {
    key: 'is_active',
    type: 'boolean',
    label: 'Активен',
    description: 'Пользователь может входить в систему',
  },
  {
    key: 'role',
    type: 'select',
    label: 'Роль',
    description: 'Уровень доступа пользователя',
    options: ROLES.map(r => ({ value: r.value, label: r.label })),
  },
];

const META_FIELDS: FieldConfig[] = [
  { key: 'id', type: 'code', label: 'ID', editable: false },
  { key: 'created_at', type: 'date', label: 'Создан', editable: false },
  { key: 'updated_at', type: 'date', label: 'Обновлен', editable: false },
];

/* ─── Component ─── */

export function UserPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const showError = useErrorToast();
  const showSuccess = useSuccessToast();

  const isNew = !id || id === 'new';
  const modeParam = searchParams.get('mode');
  const mode: EntityPageMode = isNew ? 'create' : (modeParam as EntityPageMode) || 'view';

  const [formData, setFormData] = useState({
    login: '',
    email: '',
    password: '',
    role: 'reader' as User['role'],
    tenant_ids: [] as string[],
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showSetPassword, setShowSetPassword] = useState(false);
  const [setPasswordSaving, setSetPasswordSaving] = useState(false);

  // ─── Queries ───
  const { data: user, isLoading, refetch } = useUser(id);
  const { tenants } = useTenants();

  // ─── Sync form ←→ API ───
  useEffect(() => {
    if (user) {
      setFormData({
        login: user.login || '',
        email: user.email || '',
        password: '',
        role: user.role || 'reader',
        tenant_ids: user.tenant_id ? [user.tenant_id] : [],
        is_active: user.is_active,
      });
    }
  }, [user]);

  useEffect(() => {
    if (isNew && tenants?.length && formData.tenant_ids.length === 0) {
      setFormData(prev => ({ ...prev, tenant_ids: [tenants[0].id] }));
    }
  }, [isNew, tenants, formData.tenant_ids]);

  // ─── Mutations ───
  const createMutation = useCreateUser();
  const updateMutation = useUpdateUser();
  const deleteMutation = useDeleteUser();
  const setPasswordMutation = useSetUserPassword();

  // ─── Handlers ───
  const handleFieldChange = (key: string, value: any) => {
    if (key === 'tenant_id') {
      setFormData(prev => ({ ...prev, tenant_ids: value ? [value] : [] }));
    } else {
      setFormData(prev => ({ ...prev, [key]: value }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        if (!formData.login.trim()) { showError('Логин обязателен'); return; }
        if (!formData.password.trim()) { showError('Пароль обязателен'); return; }
        await createMutation.mutateAsync({
          login: formData.login,
          email: formData.email || undefined,
          password: formData.password,
          role: formData.role,
          tenant_ids: formData.tenant_ids,
          is_active: formData.is_active,
        });
        showSuccess('Пользователь создан');
        navigate('/admin/users');
      } else {
        await updateMutation.mutateAsync({
          id: id!,
          data: {
            email: formData.email || undefined,
            role: formData.role,
            is_active: formData.is_active,
            tenant_ids: formData.tenant_ids,
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

  const handleEdit = () => setSearchParams({ mode: 'edit' });

  const handleCancel = () => {
    if (isNew) {
      navigate('/admin/users');
    } else {
      if (user) {
        setFormData({
          login: user.login || '',
          email: user.email || '',
          password: '',
          role: user.role || 'reader',
          tenant_ids: user.tenant_id ? [user.tenant_id] : [],
          is_active: user.is_active,
        });
      }
      setSearchParams({});
    }
  };

  const handleDelete = () => setShowDeleteConfirm(true);

  const handleDeleteConfirm = async () => {
    try {
      await deleteMutation.mutateAsync(id!);
      showSuccess('Пользователь удалён');
      navigate('/admin/users');
      setShowDeleteConfirm(false);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  const handleSetPassword = async (newPassword: string) => {
    if (!id) return;
    setSetPasswordSaving(true);
    try {
      await setPasswordMutation.mutateAsync({ id, newPassword });
      showSuccess('Пароль установлен');
      setShowSetPassword(false);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Ошибка установки пароля');
    } finally {
      setSetPasswordSaving(false);
    }
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Пользователи', href: '/admin/users' },
    { label: user?.login || 'Новый пользователь' },
  ];

  // ─── Derived data for blocks ───
  const infoData = (mode === 'edit' || isNew)
    ? { ...formData, tenant_id: formData.tenant_ids[0] ?? '' }
    : {
        login: user?.login || '',
        email: user?.email || '',
        password: '',
        tenant_id: user?.tenant_id || '',
      };

  const statusData = mode === 'edit' ? formData : {
    is_active: user?.is_active || false,
    role: user?.role || 'reader',
  };

  const metaData = {
    id: user?.id || '',
    created_at: user?.created_at || '',
    updated_at: user?.updated_at || '',
  };

  // Options for selects
  const tenantOptions = [
    { value: '', label: '— Не выбран —' },
    ...(tenants || []).map((t: Tenant) => ({
      value: t.id,
      label: t.name,
    })),
  ];

  const infoFields: FieldConfig[] = BASE_INFO_FIELDS.map(f =>
    f.key === 'tenant_id' ? { ...f, options: tenantOptions } : f as FieldConfig
  );

  const infoFieldsCreate: FieldConfig[] = BASE_INFO_FIELDS_CREATE.map(f =>
    f.key === 'tenant_id' ? { ...f, options: tenantOptions } : f as FieldConfig
  );

  const isLocalAccount = !user || (user.auth_provider ?? 'local') === 'local';

  // ─── Create mode ───
  if (isNew) {
    return (
      <>
        <EntityPageV2
          title="Новый пользователь"
          mode={mode}
          saving={saving}
          breadcrumbs={breadcrumbs}
          backPath="/admin/users"
          onSave={handleSave}
          onCancel={handleCancel}
        >
          <Tab title="Создание" layout="single">
            <Block
              title="Основная информация"
              icon="user"
              iconVariant="info"
              width="1/2"
              fields={infoFieldsCreate}
              data={infoData}
              editable={true}
              onChange={handleFieldChange}
              headerActions={
                <Button size="sm" variant="outline" onClick={() => setShowSetPassword(true)} type="button">
                  Установить пароль
                </Button>
              }
            />
            <Block
              title="Статус и роль"
              icon="shield"
              iconVariant="warning"
              width="full"
              fields={STATUS_FIELDS}
              data={formData}
              editable={true}
              onChange={handleFieldChange}
            />
          </Tab>
        </EntityPageV2>
        <SetPasswordModal
          open={showSetPassword}
          onClose={() => setShowSetPassword(false)}
          onConfirm={(pwd) => { setFormData(prev => ({ ...prev, password: pwd })); setShowSetPassword(false); }}
          saving={false}
        />
      </>
    );
  }

  // ─── View / Edit mode ───
  return (
    <>
      <EntityPageV2
        title={user?.login || 'Пользователь'}
        mode={mode}
        loading={isLoading}
        saving={saving}
        breadcrumbs={breadcrumbs}
        onSave={handleSave}
        onCancel={handleCancel}
        onDelete={handleDelete}
      >
        <Tab
          title="Обзор"
          layout="grid"
          id="overview"
          actions={
            mode === 'view' ? [
              <Button key="edit" onClick={handleEdit}>Редактировать</Button>,
              ...(isLocalAccount ? [
                <Button key="set-pwd" variant="outline" onClick={() => setShowSetPassword(true)}>
                  Установить пароль
                </Button>,
              ] : []),
            ] : mode === 'edit' ? [
              <Button key="save" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>,
              <Button key="cancel" variant="outline" onClick={handleCancel}>Отмена</Button>,
            ] : []
          }
        >
          {/* Row 1: Info (1/2) + Tenant (1/2) */}
          <Block
            title="Основная информация"
            icon="user"
            iconVariant="info"
            width="1/2"
            fields={infoFields}
            data={infoData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />
          {/* Row 2: Status (1/2) + Meta (1/2) */}
          <Block
            title="Статус и роль"
            icon="shield"
            iconVariant="warning"
            width="1/2"
            fields={STATUS_FIELDS}
            data={statusData}
            editable={mode === 'edit'}
            onChange={handleFieldChange}
          />

          <Block
            title="Метаданные"
            icon="database"
            iconVariant="info"
            width="1/2"
            fields={META_FIELDS}
            data={metaData}
          />
        </Tab>

        {!isNew && (
        <Tab 
          title="RBAC правила" 
          layout="full"
          id="rbac"
        >
            <RBACRulesTable mode="user" ownerId={id} />
        </Tab>
        )}
      </EntityPageV2>

      <SetPasswordModal
        open={showSetPassword}
        onClose={() => setShowSetPassword(false)}
        onConfirm={handleSetPassword}
        saving={setPasswordSaving}
      />

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Удалить пользователя?"
        message={
          <div>
            <p>Вы уверены, что хотите удалить пользователя <strong>{user?.login}</strong>?</p>
            <p>Это действие нельзя отменить.</p>
          </div>
        }
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
